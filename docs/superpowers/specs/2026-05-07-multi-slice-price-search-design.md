# Multi-slice price search — design

## Problem

The RapidAPI Amazon search endpoint returns at most ~50 results per call. With `sort_by=HIGHEST_PRICE` (current behavior), all results cluster near the top of the requested price range. A query with `--min-price 0 --max-price 1000` returns mostly $700–$1000 items; the middle and lower bands of the range are never seen.

Result: poor price diversity in the candidate pool that Claude reranks. The user is paying for "novel finds across a price range" but only sees a slice.

## Goal

Produce ~30 price-diverse candidates per keyword by issuing 3 RapidAPI calls anchored to different parts of the price range, then dedup and feed to the existing Claude rerank stage.

## Non-goals

- Changing `rank.py` or the Claude prompt.
- Changing the report template.
- Adding new CLI/web flags. The existing `--min-price` / `--max-price` (and their web form equivalents) keep their meaning.
- Increasing the per-call result count (capped by RapidAPI).

## Approach

Hybrid slicing. Three calls per keyword:

| Call | Range                          | Sort            | Take |
|------|--------------------------------|-----------------|------|
| high | `[min, max]`                   | `HIGHEST_PRICE` | 10   |
| low  | `[min, max]`                   | `LOWEST_PRICE`  | 10   |
| mid  | `[min + span/3, max - span/3]` | `HIGHEST_PRICE` | 10   |

where `span = max - min`. Pool the results, dedup by ASIN, return the deduped list (up to 30).

## Component changes

### `amazon_report/fetch.py`

Add `sort_by` parameter to `search()`:

```python
def search(
    keyword: str,
    api_key: str,
    session: requests.Session | None = None,
    max_price: float = DEFAULT_MAX_PRICE,
    min_price: float = DEFAULT_MIN_PRICE,
    sort_by: str = "HIGHEST_PRICE",
) -> list[Product]:
    ...
    params["sort_by"] = sort_by
```

Add new `multi_search()`:

```python
PER_CALL_CAP = 10
MID_SLICE_MIN_SPAN = 5.0  # below this, skip the mid call

def multi_search(
    keyword: str,
    api_key: str,
    session: requests.Session | None = None,
    max_price: float = DEFAULT_MAX_PRICE,
    min_price: float = DEFAULT_MIN_PRICE,
) -> list[Product]:
    """Three price-anchored calls, deduped by ASIN. Up to ~30 products."""
    span = max_price - min_price
    calls: list[tuple[float, float, str]] = [
        (min_price, max_price, "HIGHEST_PRICE"),
        (min_price, max_price, "LOWEST_PRICE"),
    ]
    if span >= MID_SLICE_MIN_SPAN:
        calls.append((min_price + span / 3, max_price - span / 3, "HIGHEST_PRICE"))

    pool: list[Product] = []
    errors: list[str] = []
    for lo, hi, sort in calls:
        try:
            results = search(keyword, api_key, session, max_price=hi, min_price=lo, sort_by=sort)
        except FetchError as e:
            errors.append(f"{sort}[{lo:g}-{hi:g}]: {e}")
            continue
        pool.extend(results[:PER_CALL_CAP])

    if not pool and errors:
        raise FetchError("; ".join(errors))

    seen: set[str] = set()
    deduped: list[Product] = []
    for p in pool:
        if p["asin"] in seen:
            continue
        seen.add(p["asin"])
        deduped.append(p)
    return deduped
```

Notes:
- `search()` keeps its current default sort so existing callers and tests are unchanged.
- `multi_search()` swallows partial failures (one bad call shouldn't kill the keyword) but raises if all calls fail.
- Logging of partial failures is the caller's job (use the returned products vs. expected 3-call yield to detect).

### `amazon_report/main.py`

Replace the `search(...)` call in the keyword loop with `multi_search(...)`. Keep the existing per-keyword stderr line. The `_dedup_by_asin` step in main is now redundant within a single keyword but still useful across keywords — leave it.

### `amazon_report/web.py`

Same one-line swap as main.py (whatever the equivalent fetch invocation is in the web handler).

### `amazon_report/rank.py`

No change. ~30 candidates per keyword stays well within the existing token budget.

## Edge cases

- **`min_price == max_price`** (or span < `MID_SLICE_MIN_SPAN`): mid call skipped; user gets up to 20 candidates from high+low, which is fine for a tight range.
- **`min_price == 0`**: `LOWEST_PRICE` call may be dominated by $0–$5 items; that's the desired behavior — Claude reranks.
- **One API call returns 429 after retries**: caught as `FetchError`, logged, other calls proceed. If all 3 fail, the keyword fails the same way it does today.
- **Heavy ASIN overlap between calls**: deduped pool may be smaller than 30. Acceptable — diversity not quantity.

## Cost / quota

3× RapidAPI quota per keyword. README gets a one-line note in the "How it works" / pricing section.

## Testing

### Unit (new tests in `tests/test_fetch.py`)

- `test_multi_search_dedups_by_asin`: monkey-patch `search` to return three lists with overlap; assert deduped output preserves first-seen order.
- `test_multi_search_caps_per_call`: monkey-patched `search` returns 25 items; assert only the first 10 from each call enter the pool.
- `test_multi_search_skips_mid_for_tight_range`: with `span < MID_SLICE_MIN_SPAN`, assert exactly 2 underlying `search` calls.
- `test_multi_search_partial_failure`: one of the three `search` calls raises `FetchError`; assert the function still returns the other calls' products.
- `test_multi_search_total_failure`: all three raise; assert `FetchError` propagates with combined messages.
- `test_search_passes_sort_by`: assert `sort_by` parameter reaches the request `params`.

### Manual verification

Run the original failing case:

```
amazon-report "headphones" --max-price 1000
```

Inspect the report: confirm price spread covers low ($5–$50), mid ($100–$300), and high ($500–$1000) bands rather than clustering at the top.

## Migration / backward compatibility

- No CLI surface change.
- No web form change.
- `search()` signature gains an optional kwarg with a default that matches today's behavior — existing tests keep passing.
