# amazon-report

**Find the weirdest, most delightful junk on Amazon — automatically.**

A tiny Python CLI that searches Amazon for cheap stuff, asks Claude to pick the
top 10 most *novel* items, and drops a slick HTML report in your `reports/`
folder. Wind-up boat-motor coffee mixers. LED lightsaber chopsticks.
Vomiting-chicken egg separators. The kind of thing you didn't know existed and
now mildly need.

![example report](example.png)

## What this does

1. Hits the RapidAPI "Real-Time Amazon Data" endpoint for each keyword you
   pass.
2. Filters to items under your price cap (default $20).
3. Sends the candidates to **Claude Haiku 4.5** with a forced tool call so the
   ranking is structured, deterministic, and never hallucinates an ASIN.
4. Renders the top 10 to a self-contained HTML page — open it locally, ship it
   to friends, drop it in a Slack DM.

No databases, no servers, no auth flows. One command in, one HTML file out.

## Quickstart

```bash
git clone <this-repo> && cd amazonian
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# edit .env and fill in RAPIDAPI_KEY + ANTHROPIC_API_KEY
```

Then:

```bash
python -m amazon_report "unique gadgets"
python -m amazon_report --max-price 10 "weird kitchen tools" "office gag gifts"
python -m amazon_report --max-price 50 "drone" "smart home gadgets"
```

Output:

```
Fetching candidates for 2 keyword(s) under $10...
  - "weird kitchen tools": 31 under $10
  - "office gag gifts":    27 under $10
Ranking 54 candidates with Claude...
Wrote reports/report-2026-05-06-2137.html
```

Open it:

```bash
open reports/report-*.html   # macOS
xdg-open reports/report-*.html   # Linux
```

## CLI

```
amazon-report [-h] [--max-price MAX_PRICE] keywords [keywords ...]

positional:
  keywords              one or more search keywords (quote multi-word phrases)

options:
  --max-price MAX_PRICE price cap in USD (default: 20)
```

## Why it exists

Marketplace search is great at "what I want." It's terrible at "surprise me
with something delightful for under $15." This script flips the lens: it lets
a curious LLM with no purchase intent skim a few dozen results and pick the
ones that are weirdly inventive, oddly specific, or unapologetically silly.

It's a fun, ~400-line excuse to play with:

- **Claude tool-use** for structured output (no JSON-parsing prayers)
- **Prompt caching** on the system prompt
- **A clean three-module architecture** (`fetch`, `rank`, `render`) where the
  pure-function core is fully unit-tested and the I/O is mocked at the edges

## Keys

- `RAPIDAPI_KEY` — sign up at <https://rapidapi.com>, subscribe (free tier
  exists) to "Real-Time Amazon Data" by *letscrape*.
- `ANTHROPIC_API_KEY` — <https://console.anthropic.com>.

Both go in a local `.env` file. `.env` is gitignored — never commit your keys.

## Tests

```bash
pytest
```

27 tests, all hermetic. No real API calls in the suite.

## Architecture

```
amazon_report/
├── fetch.py     # RapidAPI client + JSON → Product (with retries)
├── rank.py      # Claude tool-use → ranked top-10
├── render.py    # Jinja2 → self-contained HTML
└── main.py      # argparse + glue
```

Each module is a pure function plus a thin I/O wrapper. Swap the fetch source,
the LLM, or the renderer independently.

## License

MIT — go forth and find weird stuff.
