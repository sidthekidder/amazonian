# Amazon Novelty Product Report — Design

**Status:** Approved 2026-05-06
**Owner:** sidthekid

## Goal

A Python CLI script that searches Amazon for products under $20 by keyword, has Claude rank them by novelty/uniqueness, and outputs an HTML report of the top 10.

## Non-Goals

- Live price tracking, alerts, or scheduled runs.
- Affiliate-link injection.
- Coverage of other marketplaces (eBay, Etsy, etc.).
- A web UI or service — this is a one-shot CLI.

## User Flow

```
$ python -m amazon_report "unique gadgets" "weird kitchen tools"
Fetching candidates for 2 keyword(s)...
  - "unique gadgets": 47 under $20
  - "weird kitchen tools": 38 under $20
Ranking 85 candidates with Claude...
Wrote reports/report-2026-05-06-1432.html
```

User opens the HTML file in a browser and sees a card grid of the top 10 novel products with image, title, price, novelty score, one-line reason, and an "View on Amazon" link.

## Architecture

```
CLI args (keywords)
  ↓
fetch.py     RapidAPI "Real-Time Amazon Data" /search per keyword
             → filter price < $20
             → dedup by ASIN across keywords
  ↓ list[Product]
rank.py      Single Claude batch prompt (claude-haiku-4-5-20251001)
             → structured JSON: top 10 with novelty_score + reason
             → uses prompt caching on system prompt
  ↓ list[RankedProduct]
render.py    Jinja2 template → self-contained HTML
  ↓
reports/report-YYYY-MM-DD-HHMM.html
```

## Modules

Each file is intentionally small (~50-100 lines) and independently testable.

### `models.py`
TypedDicts:
- `Product`: `asin: str`, `title: str`, `price: float`, `image_url: str`, `product_url: str`, `rating: float | None`, `description: str | None`
- `RankedProduct`: `Product` + `novelty_score: int` (1-10) + `reason: str` (≤140 chars)

### `fetch.py`
- `search(keyword: str, http: requests.Session) -> list[Product]`
- Calls `https://real-time-amazon-data.p.rapidapi.com/search` with params `{"query": keyword, "country": "US"}`.
- Headers: `X-RapidAPI-Key`, `X-RapidAPI-Host`.
- Parses response, filters items where `price < 20.0`, normalizes into `Product`.
- Returns `[]` if endpoint returns no results.
- Retries: 3x exponential backoff (1s, 2s, 4s) on 429 / 5xx via `requests`'s adapter or a small helper. After retries, raises a domain error with a clear message.

### `rank.py`
- `rank(products: list[Product]) -> list[RankedProduct]`
- Sends one Anthropic Messages API call:
  - Model: `claude-haiku-4-5-20251001`
  - System prompt: instructions for novelty judging (cached via `cache_control: {"type": "ephemeral"}`).
  - User content: numbered JSON list of candidates (asin, title, price, description truncated to 200 chars).
  - Uses Anthropic tool-calling for structured output: a single tool `submit_ranking` with input schema `{"top10": [{"asin": str, "novelty_score": int (1-10), "reason": str (≤140 chars)}]}`. `tool_choice` forces this tool. This is more reliable than instructing JSON in free-form text.
- Joins ranking back to source `Product` records by ASIN.
- If model returns malformed JSON: one re-prompt asking for valid JSON only. If still bad → raise.
- If fewer than 10 candidates: rank all of them.

### `render.py`
- `render(ranked: list[RankedProduct], out_path: Path) -> None`
- Jinja2 template `templates/report.html.j2` (sibling to module).
- Self-contained HTML: inline CSS, image tags pointing at Amazon CDN URLs (no asset download).
- Card layout: thumbnail, title (truncated), price, novelty score badge (1-10), one-line reason, "View on Amazon" button → `product_url`.
- Header shows: keywords used, date/time, candidate count, source ("RapidAPI Real-Time Amazon Data").

### `main.py`
- `argparse`: positional `keywords` (one or more, required).
- Loads `.env` via `python-dotenv`.
- Validates `RAPIDAPI_KEY` and `ANTHROPIC_API_KEY` are set; if not, prints which is missing and exits 1.
- Orchestrates fetch → dedup → rank → render. Prints progress lines.
- Writes to `reports/report-{ISO local date-time minute}.html`. Creates `reports/` if missing.

## Config

- `.env` (gitignored) with `RAPIDAPI_KEY=...` and `ANTHROPIC_API_KEY=...`.
- `.env.example` checked in with placeholder keys.
- No other config; defaults are constants in code (top-N=10, price cap=$20, model id, RapidAPI host).

## Error Handling

| Scenario | Behavior |
|---|---|
| Missing env var | Exit 1 at startup with `Missing RAPIDAPI_KEY — copy .env.example to .env and fill in.` |
| RapidAPI 429 / 5xx | Backoff retry 3x; then raise with message including status + body excerpt |
| RapidAPI 401 / 403 | No retry; clear "Invalid or unauthorized RAPIDAPI_KEY" message, exit 1 |
| Zero candidates < $20 | Print friendly "No products under $20 found for keywords: [...]"; skip Claude call; exit 0 |
| Anthropic call fails | Surface SDK exception; no retry (Anthropic SDK has its own retries) |
| Malformed model JSON | One re-prompt; if still bad, exit 1 with the raw response logged to stderr |

## Testing

Tests use `pytest`. No live API calls in the test suite.

- `tests/fixtures/rapidapi_search.json` — recorded RapidAPI response (sanitized).
- `tests/test_fetch.py` — feeds fixture into a parser shim, asserts price filter and field mapping.
- `tests/test_rank.py` — stubs Anthropic client to return a canned `top10` JSON; asserts join-by-ASIN, ordering, length cap.
- `tests/test_render.py` — passes 3 fixture `RankedProduct`s to renderer, asserts substrings in output (title, price, reason, link).
- Smoke test = manually running `python -m amazon_report "unique gadgets"` once with real keys.

## Cost Estimate

- Per run: 1-N RapidAPI requests (one per keyword) + 1 Claude call.
- Claude tokens: ~50-100 candidates × ~50 tokens each ≈ 3-5K input + ~500 output. At Haiku 4.5 pricing → well under $0.01 per report.
- RapidAPI free tier covers ~500 requests/month → effectively free for personal use.

## Project Layout

```
amazonian/
├── amazon_report/
│   ├── __init__.py
│   ├── __main__.py        # entry: python -m amazon_report
│   ├── main.py
│   ├── models.py
│   ├── fetch.py
│   ├── rank.py
│   ├── render.py
│   └── templates/
│       └── report.html.j2
├── tests/
│   ├── fixtures/
│   │   └── rapidapi_search.json
│   ├── test_fetch.py
│   ├── test_rank.py
│   └── test_render.py
├── reports/               # gitignored, created on first run
├── docs/superpowers/specs/
│   └── 2026-05-06-amazon-product-report-design.md
├── .env.example
├── .gitignore
├── pyproject.toml         # deps + pytest config
└── README.md
```

## Dependencies

- `anthropic` — Claude SDK
- `requests` — RapidAPI HTTP
- `python-dotenv` — env loading
- `jinja2` — HTML templating
- `pytest` (dev only)
