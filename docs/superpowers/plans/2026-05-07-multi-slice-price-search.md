# Multi-slice price search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single biased RapidAPI search call with three price-anchored calls (high / low / mid-third), deduped to ~30 candidates per keyword, then reranked by the existing Claude pipeline.

**Architecture:** Add `sort_by` to `search()` and a new `multi_search()` orchestrator in `amazon_report/fetch.py`. Swap the per-keyword caller in `main.py` and `web.py` from `search` → `multi_search`. No changes to `rank.py`, `render.py`, templates, or CLI/web surface.

**Tech Stack:** Python 3.11, `requests`, `pytest`, `pytest-mock` (already used via `monkeypatch` + `MagicMock`).

**Spec:** [`docs/superpowers/specs/2026-05-07-multi-slice-price-search-design.md`](../specs/2026-05-07-multi-slice-price-search-design.md)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `amazon_report/fetch.py` | Modify | Add `sort_by` kwarg to `search()`; add `multi_search()` orchestrator and `PER_CALL_CAP` / `MID_SLICE_MIN_SPAN` constants. |
| `amazon_report/main.py` | Modify | Replace `search(...)` with `multi_search(...)` in keyword loop; update import. |
| `amazon_report/web.py` | Modify | Same swap as main.py. |
| `tests/test_fetch.py` | Modify | Add tests for `sort_by` plumbing and the new `multi_search` behavior. |
| `README.md` | Modify | One-line note about 3× RapidAPI quota per keyword. |

---

## Task 1: Add `sort_by` parameter to `search()`

Threads a sort-order string through to the RapidAPI request. Default preserves today's behavior.

**Files:**
- Modify: `amazon_report/fetch.py:72-93`
- Test: `tests/test_fetch.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_fetch.py` (append to the bottom of the file):

```python
def test_search_passes_sort_by_param(monkeypatch):
    monkeypatch.setattr("amazon_report.fetch.time.sleep", lambda *_: None)
    sess = MagicMock()
    sess.get.return_value = _FakeResp(200, FIXTURE)
    search("widgets", api_key="k", session=sess, sort_by="LOWEST_PRICE")
    _, kwargs = sess.get.call_args
    assert kwargs["params"]["sort_by"] == "LOWEST_PRICE"


def test_search_default_sort_is_highest_price(monkeypatch):
    sess = MagicMock()
    sess.get.return_value = _FakeResp(200, FIXTURE)
    search("widgets", api_key="k", session=sess)
    _, kwargs = sess.get.call_args
    assert kwargs["params"]["sort_by"] == "HIGHEST_PRICE"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fetch.py::test_search_passes_sort_by_param tests/test_fetch.py::test_search_default_sort_is_highest_price -v`

Expected: `test_search_passes_sort_by_param` FAILS with `TypeError: search() got an unexpected keyword argument 'sort_by'`. `test_search_default_sort_is_highest_price` PASSES (sort is already hardcoded to HIGHEST_PRICE).

- [ ] **Step 3: Add `sort_by` parameter to `search()`**

In `amazon_report/fetch.py`, modify the `search` function signature and the params dict (lines 72-93). Replace:

```python
def search(
    keyword: str,
    api_key: str,
    session: requests.Session | None = None,
    max_price: float = DEFAULT_MAX_PRICE,
    min_price: float = DEFAULT_MIN_PRICE,
) -> list[Product]:
    """Search RapidAPI and return parsed products in [min_price, max_price). Retries on 429/5xx."""
    sess = session or requests.Session()
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }
    params: dict[str, Any] = {
        "query": keyword,
        "country": "US",
        "sort_by": "HIGHEST_PRICE",
    }
```

with:

```python
def search(
    keyword: str,
    api_key: str,
    session: requests.Session | None = None,
    max_price: float = DEFAULT_MAX_PRICE,
    min_price: float = DEFAULT_MIN_PRICE,
    sort_by: str = "HIGHEST_PRICE",
) -> list[Product]:
    """Search RapidAPI and return parsed products in [min_price, max_price). Retries on 429/5xx."""
    sess = session or requests.Session()
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }
    params: dict[str, Any] = {
        "query": keyword,
        "country": "US",
        "sort_by": sort_by,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fetch.py -v`

Expected: All tests PASS, including the two new ones.

- [ ] **Step 5: Commit**

```bash
git add amazon_report/fetch.py tests/test_fetch.py
git commit -m "feat(fetch): add sort_by kwarg to search()"
```

---

## Task 2: Add `multi_search()` orchestrator

Three price-anchored RapidAPI calls per keyword, deduped by ASIN, capped at ~30 candidates.

**Files:**
- Modify: `amazon_report/fetch.py` (append new function and constants)
- Test: `tests/test_fetch.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_fetch.py`:

```python
from amazon_report.fetch import multi_search, PER_CALL_CAP, MID_SLICE_MIN_SPAN


def _product(asin: str, price: float):
    return {
        "asin": asin,
        "title": f"Item {asin}",
        "price": price,
        "image_url": "https://x",
        "product_url": f"https://amazon.com/dp/{asin}",
        "rating": None,
        "description": None,
    }


def test_multi_search_makes_three_calls_for_wide_range(monkeypatch):
    calls: list[dict] = []

    def fake_search(keyword, api_key, session=None, max_price=20.0, min_price=0.0, sort_by="HIGHEST_PRICE"):
        calls.append({"min": min_price, "max": max_price, "sort": sort_by})
        return []

    monkeypatch.setattr("amazon_report.fetch.search", fake_search)
    multi_search("widgets", api_key="k", min_price=0.0, max_price=300.0)
    assert len(calls) == 3
    assert calls[0] == {"min": 0.0, "max": 300.0, "sort": "HIGHEST_PRICE"}
    assert calls[1] == {"min": 0.0, "max": 300.0, "sort": "LOWEST_PRICE"}
    # span = 300; mid slice = [0 + 100, 300 - 100] = [100, 200]
    assert calls[2] == {"min": 100.0, "max": 200.0, "sort": "HIGHEST_PRICE"}


def test_multi_search_skips_mid_for_tight_range(monkeypatch):
    calls: list[dict] = []

    def fake_search(keyword, api_key, session=None, max_price=20.0, min_price=0.0, sort_by="HIGHEST_PRICE"):
        calls.append({"min": min_price, "max": max_price, "sort": sort_by})
        return []

    monkeypatch.setattr("amazon_report.fetch.search", fake_search)
    # span = 4 < MID_SLICE_MIN_SPAN (5)
    multi_search("widgets", api_key="k", min_price=10.0, max_price=14.0)
    assert len(calls) == 2
    assert all(c["max"] == 14.0 and c["min"] == 10.0 for c in calls)


def test_multi_search_caps_each_call_at_per_call_cap(monkeypatch):
    big_list_a = [_product(f"A{i}", 100.0 + i) for i in range(25)]
    big_list_b = [_product(f"B{i}", 5.0 + i) for i in range(25)]
    big_list_c = [_product(f"C{i}", 50.0 + i) for i in range(25)]
    queue = [big_list_a, big_list_b, big_list_c]

    def fake_search(*args, **kwargs):
        return queue.pop(0)

    monkeypatch.setattr("amazon_report.fetch.search", fake_search)
    out = multi_search("widgets", api_key="k", min_price=0.0, max_price=300.0)
    # 10 + 10 + 10, no overlap between A/B/C asins
    assert len(out) == 3 * PER_CALL_CAP
    asins = {p["asin"] for p in out}
    assert "A0" in asins and "A9" in asins and "A10" not in asins
    assert "B0" in asins and "B9" in asins and "B10" not in asins
    assert "C0" in asins and "C9" in asins and "C10" not in asins


def test_multi_search_dedups_by_asin(monkeypatch):
    high = [_product("X1", 250.0), _product("X2", 240.0)]
    low = [_product("X3", 5.0), _product("X1", 250.0)]  # X1 dup
    mid = [_product("X4", 150.0), _product("X2", 240.0)]  # X2 dup
    queue = [high, low, mid]

    def fake_search(*args, **kwargs):
        return queue.pop(0)

    monkeypatch.setattr("amazon_report.fetch.search", fake_search)
    out = multi_search("widgets", api_key="k", min_price=0.0, max_price=300.0)
    asins = [p["asin"] for p in out]
    # First-seen order preserved; duplicates dropped
    assert asins == ["X1", "X2", "X3", "X4"]


def test_multi_search_partial_failure_returns_remaining(monkeypatch):
    queue = [
        [_product("A1", 250.0)],
        FetchError("rate limited"),
        [_product("C1", 150.0)],
    ]

    def fake_search(*args, **kwargs):
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr("amazon_report.fetch.search", fake_search)
    out = multi_search("widgets", api_key="k", min_price=0.0, max_price=300.0)
    asins = [p["asin"] for p in out]
    assert asins == ["A1", "C1"]


def test_multi_search_total_failure_raises(monkeypatch):
    def fake_search(*args, **kwargs):
        raise FetchError("boom")

    monkeypatch.setattr("amazon_report.fetch.search", fake_search)
    with pytest.raises(FetchError, match="boom"):
        multi_search("widgets", api_key="k", min_price=0.0, max_price=300.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fetch.py -v -k multi_search`

Expected: All six new tests FAIL with `ImportError: cannot import name 'multi_search'`.

- [ ] **Step 3: Implement `multi_search()` and constants**

In `amazon_report/fetch.py`, append at the bottom of the file (after the existing `search` function):

```python
PER_CALL_CAP = 10
MID_SLICE_MIN_SPAN = 5.0


def multi_search(
    keyword: str,
    api_key: str,
    session: requests.Session | None = None,
    max_price: float = DEFAULT_MAX_PRICE,
    min_price: float = DEFAULT_MIN_PRICE,
) -> list[Product]:
    """Three price-anchored calls (high / low / middle-third), deduped by ASIN.

    Returns up to ~30 products per keyword. If all three calls fail the
    last FetchError is raised; partial failures are swallowed.
    """
    span = max_price - min_price
    calls: list[tuple[float, float, str]] = [
        (min_price, max_price, "HIGHEST_PRICE"),
        (min_price, max_price, "LOWEST_PRICE"),
    ]
    if span >= MID_SLICE_MIN_SPAN:
        calls.append((min_price + span / 3, max_price - span / 3, "HIGHEST_PRICE"))

    pool: list[Product] = []
    last_err: FetchError | None = None
    for lo, hi, sort in calls:
        try:
            results = search(
                keyword,
                api_key=api_key,
                session=session,
                max_price=hi,
                min_price=lo,
                sort_by=sort,
            )
        except FetchError as e:
            last_err = e
            continue
        pool.extend(results[:PER_CALL_CAP])

    if not pool and last_err is not None:
        raise last_err

    seen: set[str] = set()
    deduped: list[Product] = []
    for p in pool:
        if p["asin"] in seen:
            continue
        seen.add(p["asin"])
        deduped.append(p)
    return deduped
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fetch.py -v`

Expected: All tests PASS, including the six new `multi_search` tests.

- [ ] **Step 5: Commit**

```bash
git add amazon_report/fetch.py tests/test_fetch.py
git commit -m "feat(fetch): add multi_search() with 3 price-anchored calls"
```

---

## Task 3: Wire `multi_search` into the CLI

Swap the keyword-loop call in `main.py`. Logging line updates to reflect that the per-keyword count now reflects the deduped multi-call pool.

**Files:**
- Modify: `amazon_report/main.py:11` (import) and `amazon_report/main.py:108-121` (loop)
- Test: covered by the existing `multi_search` tests; manual smoke after.

- [ ] **Step 1: Update the import**

In `amazon_report/main.py`, change line 11 from:

```python
from amazon_report.fetch import search, FetchError, DEFAULT_MAX_PRICE, DEFAULT_MIN_PRICE
```

to:

```python
from amazon_report.fetch import multi_search, FetchError, DEFAULT_MAX_PRICE, DEFAULT_MIN_PRICE
```

- [ ] **Step 2: Swap the keyword-loop call**

In `amazon_report/main.py`, replace lines 108-121 (the `for kw in keywords:` block):

```python
    for kw in keywords:
        try:
            results = search(
                kw,
                api_key=env["RAPIDAPI_KEY"],
                session=session,
                max_price=max_price,
                min_price=min_price,
            )
        except FetchError as e:
            print(f"  ! \"{kw}\" failed: {e}", file=sys.stderr)
            continue
        print(f"  - \"{kw}\": {len(results)} in {range_label}")
        candidates.extend(results)
```

with:

```python
    for kw in keywords:
        try:
            results = multi_search(
                kw,
                api_key=env["RAPIDAPI_KEY"],
                session=session,
                max_price=max_price,
                min_price=min_price,
            )
        except FetchError as e:
            print(f"  ! \"{kw}\" failed: {e}", file=sys.stderr)
            continue
        print(f"  - \"{kw}\": {len(results)} in {range_label} (3-slice)")
        candidates.extend(results)
```

- [ ] **Step 3: Verify the existing test suite still passes**

Run: `pytest -v`

Expected: All tests PASS. (No tests directly exercise `main.main()`; this change is wire-only.)

- [ ] **Step 4: Commit**

```bash
git add amazon_report/main.py
git commit -m "feat(cli): use multi_search for price-diverse candidates"
```

---

## Task 4: Wire `multi_search` into the web UI

Same swap in `web.py`.

**Files:**
- Modify: `amazon_report/web.py:11-16` (import) and `amazon_report/web.py:122-134` (loop)

- [ ] **Step 1: Update the import**

In `amazon_report/web.py`, replace lines 11-16:

```python
from amazon_report.fetch import (
    DEFAULT_MAX_PRICE,
    DEFAULT_MIN_PRICE,
    FetchError,
    search,
)
```

with:

```python
from amazon_report.fetch import (
    DEFAULT_MAX_PRICE,
    DEFAULT_MIN_PRICE,
    FetchError,
    multi_search,
)
```

- [ ] **Step 2: Swap the keyword-loop call**

In `amazon_report/web.py`, replace lines 122-134 (the `for kw in keywords:` block):

```python
        for kw in keywords:
            try:
                results = search(
                    kw,
                    api_key=api_key,
                    session=session,
                    max_price=max_price,
                    min_price=min_price,
                )
            except FetchError as e:
                fetch_errors.append(f'"{kw}": {e}')
                continue
            candidates.extend(results)
        candidates = _dedup_by_asin(candidates)
```

with:

```python
        for kw in keywords:
            try:
                results = multi_search(
                    kw,
                    api_key=api_key,
                    session=session,
                    max_price=max_price,
                    min_price=min_price,
                )
            except FetchError as e:
                fetch_errors.append(f'"{kw}": {e}')
                continue
            candidates.extend(results)
        candidates = _dedup_by_asin(candidates)
```

(The `_dedup_by_asin` line stays — it now dedups across keywords, not within.)

- [ ] **Step 3: Verify the test suite still passes**

Run: `pytest -v`

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add amazon_report/web.py
git commit -m "feat(web): use multi_search for price-diverse candidates"
```

---

## Task 5: Document the 3× quota in README

A single-line note so a user running with `--max-price 1000` understands the API-call multiplier.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read the README to find the right insertion point**

Run: `grep -n "RapidAPI" README.md`

Pick a "How it works" / "API usage" section. If none exists, append a one-line note at the end of the "Use it" section.

- [ ] **Step 2: Add the note**

Insert (or append, in a fitting section):

```markdown
> Each keyword issues **3 RapidAPI search calls** (high / low / middle-third) to keep candidates price-diverse and avoid clustering at the top of the range.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: note 3-call multi-slice fetch in README"
```

---

## Task 6: Manual verification

End-to-end smoke against the original failing case.

- [ ] **Step 1: Run the CLI against a wide range**

Run (requires a populated `.env`):

```bash
python -m amazon_report.main "headphones" --max-price 1000
```

- [ ] **Step 2: Inspect the report**

Open the generated HTML in `reports/`. Expected:

- The candidate count printed to stdout is closer to ~30 (vs. ~16 before).
- Product prices span low ($5–$50), mid ($100–$300), and high ($500–$1000) bands rather than clustering near $1000.

- [ ] **Step 3: Smoke the web UI**

Run: `python -m amazon_report.web`

In the browser at `http://127.0.0.1:8000/`, search `headphones` with min=0, max=1000. Expected: same diversity as the CLI.

- [ ] **Step 4: If verification passes, push**

```bash
git push origin main
```

---

## Self-review notes

- All spec sections covered: Task 1 (sort_by), Task 2 (multi_search + slicing + dedup + edge cases + partial failure), Task 3 (main.py wire), Task 4 (web.py wire), Task 5 (README), Task 6 (manual verification).
- No placeholders. Every step shows the actual code or command.
- Function signatures: `search(..., sort_by="HIGHEST_PRICE")` and `multi_search(keyword, api_key, session, max_price, min_price)` match between Task 1, Task 2, Task 3, Task 4.
- Constants `PER_CALL_CAP=10` and `MID_SLICE_MIN_SPAN=5.0` defined in Task 2 and referenced in Task 2 tests.
- `MID_SLICE_MIN_SPAN=5.0` matches the spec's `< 5` example for the tight-range branch.
