# amazon-report

Python CLI that searches Amazon for products under $20 by keyword, asks Claude to rank them by novelty, and writes an HTML report.

## Setup

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -e ".[dev]"`
3. Copy `.env.example` to `.env` and fill in:
   - `RAPIDAPI_KEY` — sign up at https://rapidapi.com and subscribe (free tier) to "Real-Time Amazon Data" by letscrape
   - `ANTHROPIC_API_KEY` — from https://console.anthropic.com

## Usage

```bash
python -m amazon_report "unique gadgets" "weird kitchen tools"
```

Writes `reports/report-YYYY-MM-DD-HHMM.html` and prints the path.

## Tests

```bash
pytest
```
