# Amazon Novelty Product Report — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI that searches Amazon for products under $20 by keyword, has Claude rank them by novelty, and outputs an HTML report of the top 10.

**Architecture:** Three pure-function modules (`fetch`, `rank`, `render`) glued by `main.py`. `fetch` calls RapidAPI's "Real-Time Amazon Data" search endpoint and normalizes results. `rank` sends one Anthropic Messages API call (claude-haiku-4-5-20251001) using a forced tool call for structured top-10 output. `render` uses Jinja2 to produce a self-contained HTML file. All I/O lives at the edges; the parsing/ranking/rendering core is testable with fixtures and stubs.

**Tech Stack:** Python 3.11+, `anthropic` SDK, `requests`, `python-dotenv`, `jinja2`, `pytest`.

---

## Task 1: Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `amazon_report/__init__.py`
- Create: `amazon_report/__main__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "amazon-report"
version = "0.1.0"
description = "Find novel Amazon products under $20 and write an HTML report."
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40.0",
    "requests>=2.32.0",
    "python-dotenv>=1.0.1",
    "jinja2>=3.1.4",
]

[project.optional-dependencies]
dev = ["pytest>=8.0.0"]

[project.scripts]
amazon-report = "amazon_report.main:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["amazon_report*"]

[tool.setuptools.package-data]
amazon_report = ["templates/*.j2"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v"
```

- [ ] **Step 2: Create `.gitignore`**

```
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
reports/
*.egg-info/
build/
dist/
```

- [ ] **Step 3: Create `.env.example`**

```
RAPIDAPI_KEY=your_rapidapi_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

- [ ] **Step 4: Create `README.md`**

```markdown
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
```

- [ ] **Step 5: Create empty package init files**

`amazon_report/__init__.py`:
```python
```

`tests/__init__.py`:
```python
```

- [ ] **Step 6: Create `amazon_report/__main__.py`**

```python
from amazon_report.main import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Verify install works**

Run: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
Expected: installs successfully, `pytest --version` works.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore .env.example README.md amazon_report/__init__.py amazon_report/__main__.py tests/__init__.py
git commit -m "chore: scaffold amazon-report package"
```

---

## Task 2: Data Models

**Files:**
- Create: `amazon_report/models.py`

- [ ] **Step 1: Create `amazon_report/models.py`**

```python
from typing import TypedDict


class Product(TypedDict):
    asin: str
    title: str
    price: float
    image_url: str
    product_url: str
    rating: float | None
    description: str | None


class RankedProduct(TypedDict):
    asin: str
    title: str
    price: float
    image_url: str
    product_url: str
    rating: float | None
    description: str | None
    novelty_score: int
    reason: str
```

- [ ] **Step 2: Commit**

```bash
git add amazon_report/models.py
git commit -m "feat: add Product and RankedProduct typed dicts"
```

---

## Task 3: Fetch Module — Fixture and Parsing Tests

**Files:**
- Create: `tests/fixtures/rapidapi_search.json`
- Create: `tests/test_fetch.py`
- Create: `amazon_report/fetch.py`

- [ ] **Step 1: Create `tests/fixtures/rapidapi_search.json`**

This is a sanitized minimal version of a real RapidAPI Real-Time Amazon Data `/search` response. Fields not used by the parser are omitted.

```json
{
  "status": "OK",
  "request_id": "abc-123",
  "data": {
    "total_products": 4,
    "country": "US",
    "domain": "www.amazon.com",
    "products": [
      {
        "asin": "B0AAA00001",
        "product_title": "Self-Stirring Mug with USB",
        "product_price": "$14.99",
        "product_original_price": "$19.99",
        "product_star_rating": "4.3",
        "product_num_ratings": 1234,
        "product_url": "https://www.amazon.com/dp/B0AAA00001",
        "product_photo": "https://m.media-amazon.com/images/I/aaa.jpg",
        "product_minimum_offer_price": "$14.99",
        "is_prime": true
      },
      {
        "asin": "B0AAA00002",
        "product_title": "Avocado Slicer 3-in-1 Tool",
        "product_price": "$8.50",
        "product_star_rating": "4.6",
        "product_url": "https://www.amazon.com/dp/B0AAA00002",
        "product_photo": "https://m.media-amazon.com/images/I/bbb.jpg"
      },
      {
        "asin": "B0AAA00003",
        "product_title": "Premium Cookware Set",
        "product_price": "$129.99",
        "product_url": "https://www.amazon.com/dp/B0AAA00003",
        "product_photo": "https://m.media-amazon.com/images/I/ccc.jpg"
      },
      {
        "asin": "B0AAA00004",
        "product_title": "Cat-Shaped Tea Infuser",
        "product_price": null,
        "product_url": "https://www.amazon.com/dp/B0AAA00004",
        "product_photo": "https://m.media-amazon.com/images/I/ddd.jpg"
      }
    ]
  }
}
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_fetch.py`:

```python
import json
from pathlib import Path

import pytest

from amazon_report.fetch import parse_search_response, _parse_price


FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "rapidapi_search.json").read_text())


def test_parse_price_handles_dollar_string():
    assert _parse_price("$14.99") == 14.99


def test_parse_price_handles_comma():
    assert _parse_price("$1,299.00") == 1299.00


def test_parse_price_returns_none_for_missing():
    assert _parse_price(None) is None
    assert _parse_price("") is None


def test_parse_search_response_filters_to_under_20():
    products = parse_search_response(FIXTURE)
    asins = [p["asin"] for p in products]
    assert "B0AAA00001" in asins  # $14.99 — kept
    assert "B0AAA00002" in asins  # $8.50 — kept
    assert "B0AAA00003" not in asins  # $129.99 — filtered
    assert "B0AAA00004" not in asins  # null price — filtered


def test_parse_search_response_normalizes_fields():
    products = parse_search_response(FIXTURE)
    p = next(p for p in products if p["asin"] == "B0AAA00001")
    assert p["title"] == "Self-Stirring Mug with USB"
    assert p["price"] == 14.99
    assert p["image_url"] == "https://m.media-amazon.com/images/I/aaa.jpg"
    assert p["product_url"] == "https://www.amazon.com/dp/B0AAA00001"
    assert p["rating"] == 4.3


def test_parse_search_response_handles_missing_optional_rating():
    products = parse_search_response(FIXTURE)
    p = next(p for p in products if p["asin"] == "B0AAA00002")
    # B0AAA00002 has rating, but verify the missing-rating path with a synthetic input
    synthetic = {"data": {"products": [{
        "asin": "X1", "product_title": "X", "product_price": "$5.00",
        "product_url": "https://x", "product_photo": "https://x"
    }]}}
    out = parse_search_response(synthetic)
    assert out[0]["rating"] is None


def test_parse_search_response_empty_when_no_products():
    assert parse_search_response({"data": {"products": []}}) == []
    assert parse_search_response({"data": {}}) == []
    assert parse_search_response({}) == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_fetch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'amazon_report.fetch'`

- [ ] **Step 4: Implement `amazon_report/fetch.py`**

```python
import time
from typing import Any

import requests

from amazon_report.models import Product

RAPIDAPI_HOST = "real-time-amazon-data.p.rapidapi.com"
SEARCH_URL = f"https://{RAPIDAPI_HOST}/search"
PRICE_CAP = 20.0
RETRIES = 3
BACKOFF_BASE = 1.0


class FetchError(Exception):
    pass


def _parse_price(raw: Any) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = s.replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _parse_rating(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def parse_search_response(payload: dict[str, Any]) -> list[Product]:
    """Pure function: take RapidAPI JSON, return Products with price < PRICE_CAP."""
    items = payload.get("data", {}).get("products", []) or []
    out: list[Product] = []
    for item in items:
        price = _parse_price(item.get("product_price"))
        if price is None or price >= PRICE_CAP:
            continue
        asin = item.get("asin")
        title = item.get("product_title")
        image_url = item.get("product_photo")
        product_url = item.get("product_url")
        if not (asin and title and image_url and product_url):
            continue
        out.append(Product(
            asin=asin,
            title=title,
            price=price,
            image_url=image_url,
            product_url=product_url,
            rating=_parse_rating(item.get("product_star_rating")),
            description=item.get("product_description"),
        ))
    return out


def search(keyword: str, api_key: str, session: requests.Session | None = None) -> list[Product]:
    """Search RapidAPI and return parsed products under $20. Retries on 429/5xx."""
    sess = session or requests.Session()
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }
    params = {"query": keyword, "country": "US"}
    last_err: Exception | None = None
    for attempt in range(RETRIES):
        try:
            resp = sess.get(SEARCH_URL, headers=headers, params=params, timeout=20)
            if resp.status_code in (401, 403):
                raise FetchError(
                    f"RapidAPI auth failed ({resp.status_code}). Check RAPIDAPI_KEY."
                )
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                last_err = FetchError(f"RapidAPI {resp.status_code}: {resp.text[:200]}")
                time.sleep(BACKOFF_BASE * (2 ** attempt))
                continue
            resp.raise_for_status()
            return parse_search_response(resp.json())
        except requests.RequestException as e:
            last_err = e
            time.sleep(BACKOFF_BASE * (2 ** attempt))
    raise FetchError(f"RapidAPI request failed after {RETRIES} retries: {last_err}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_fetch.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/rapidapi_search.json tests/test_fetch.py amazon_report/fetch.py
git commit -m "feat: parse RapidAPI search results, filter under \$20"
```

---

## Task 4: Fetch Module — Retry / Auth Tests

**Files:**
- Modify: `tests/test_fetch.py`

- [ ] **Step 1: Append retry/auth tests**

Add to the end of `tests/test_fetch.py`:

```python
from unittest.mock import MagicMock

from amazon_report.fetch import search, FetchError


class _FakeResp:
    def __init__(self, status: int, body: dict | None = None, text: str = ""):
        self.status_code = status
        self._body = body or {}
        self.text = text

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def test_search_returns_parsed_products(monkeypatch):
    sess = MagicMock()
    sess.get.return_value = _FakeResp(200, FIXTURE)
    out = search("widgets", api_key="k", session=sess)
    assert len(out) == 2  # only the two under $20 with full fields
    sess.get.assert_called_once()


def test_search_raises_on_401():
    sess = MagicMock()
    sess.get.return_value = _FakeResp(401, text="unauthorized")
    with pytest.raises(FetchError, match="auth failed"):
        search("widgets", api_key="bad", session=sess)


def test_search_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("amazon_report.fetch.time.sleep", lambda *_: None)
    sess = MagicMock()
    sess.get.side_effect = [
        _FakeResp(429, text="rate limited"),
        _FakeResp(200, FIXTURE),
    ]
    out = search("widgets", api_key="k", session=sess)
    assert len(out) == 2
    assert sess.get.call_count == 2


def test_search_gives_up_after_retries(monkeypatch):
    monkeypatch.setattr("amazon_report.fetch.time.sleep", lambda *_: None)
    sess = MagicMock()
    sess.get.return_value = _FakeResp(503, text="down")
    with pytest.raises(FetchError, match="failed after"):
        search("widgets", api_key="k", session=sess)
    assert sess.get.call_count == 3  # RETRIES
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_fetch.py -v`
Expected: 11 passed (7 from Task 3 + 4 new).

- [ ] **Step 3: Commit**

```bash
git add tests/test_fetch.py
git commit -m "test: cover RapidAPI retry and auth failure paths"
```

---

## Task 5: Rank Module — Stubbed Anthropic Client

**Files:**
- Create: `tests/test_rank.py`
- Create: `amazon_report/rank.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rank.py`:

```python
from unittest.mock import MagicMock

import pytest

from amazon_report.models import Product
from amazon_report.rank import rank, RankError, _build_user_message


def _product(asin: str, title: str, price: float = 9.99) -> Product:
    return Product(
        asin=asin, title=title, price=price,
        image_url=f"https://img/{asin}.jpg",
        product_url=f"https://amazon.com/dp/{asin}",
        rating=4.5, description=None,
    )


class _FakeContentBlock:
    def __init__(self, type_: str, name: str = "", input_: dict | None = None):
        self.type = type_
        self.name = name
        self.input = input_ or {}


class _FakeMessage:
    def __init__(self, blocks):
        self.content = blocks


def _make_client(top10: list[dict]) -> MagicMock:
    client = MagicMock()
    block = _FakeContentBlock("tool_use", name="submit_ranking", input_={"top10": top10})
    client.messages.create.return_value = _FakeMessage([block])
    return client


def test_rank_joins_by_asin_and_preserves_order():
    products = [
        _product("A1", "Self-Stirring Mug"),
        _product("A2", "Avocado Slicer"),
        _product("A3", "Cat Tea Infuser"),
    ]
    top10 = [
        {"asin": "A3", "novelty_score": 9, "reason": "Cat-shaped, whimsical."},
        {"asin": "A1", "novelty_score": 7, "reason": "USB self-stirring is unusual."},
    ]
    out = rank(products, client=_make_client(top10))
    assert [r["asin"] for r in out] == ["A3", "A1"]
    assert out[0]["title"] == "Cat Tea Infuser"
    assert out[0]["novelty_score"] == 9
    assert out[0]["reason"] == "Cat-shaped, whimsical."
    assert out[1]["price"] == 9.99


def test_rank_drops_unknown_asins_from_model():
    products = [_product("A1", "Mug")]
    top10 = [{"asin": "GHOST", "novelty_score": 10, "reason": "x"},
             {"asin": "A1", "novelty_score": 5, "reason": "ok"}]
    out = rank(products, client=_make_client(top10))
    assert len(out) == 1
    assert out[0]["asin"] == "A1"


def test_rank_returns_empty_for_empty_input():
    client = MagicMock()
    out = rank([], client=client)
    assert out == []
    client.messages.create.assert_not_called()


def test_rank_caps_at_10():
    products = [_product(f"A{i}", f"item {i}") for i in range(20)]
    top10 = [{"asin": f"A{i}", "novelty_score": 10 - i % 10, "reason": "r"} for i in range(15)]
    out = rank(products, client=_make_client(top10))
    assert len(out) == 10


def test_rank_raises_when_no_tool_use_in_response():
    client = MagicMock()
    client.messages.create.return_value = _FakeMessage([_FakeContentBlock("text")])
    # Configure the retry to also fail
    with pytest.raises(RankError):
        rank([_product("A1", "Mug")], client=client, max_retries=1)


def test_build_user_message_includes_all_candidates():
    msg = _build_user_message([_product("A1", "Mug"), _product("A2", "Slicer")])
    assert "A1" in msg
    assert "Mug" in msg
    assert "A2" in msg
    assert "Slicer" in msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rank.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'amazon_report.rank'`

- [ ] **Step 3: Implement `amazon_report/rank.py`**

```python
import json
from typing import Any

from amazon_report.models import Product, RankedProduct

MODEL = "claude-haiku-4-5-20251001"
TOP_N = 10
MAX_DESCRIPTION_CHARS = 200

SYSTEM_PROMPT = (
    "You are a product curator with sharp taste for novel, unusual, or quirky items. "
    "From a list of Amazon products under $20, pick the most NOVEL ones — things that "
    "feel inventive, surprising, weirdly specific, or delightfully unique. Avoid generic, "
    "commodity, or obviously-mass-produced items. Score 1-10 where 10 is wildly novel. "
    "Always return your answer via the submit_ranking tool. Reasons must be ≤140 characters."
)

TOOL = {
    "name": "submit_ranking",
    "description": "Submit the top novel products ranked by novelty score (highest first).",
    "input_schema": {
        "type": "object",
        "properties": {
            "top10": {
                "type": "array",
                "maxItems": TOP_N,
                "items": {
                    "type": "object",
                    "properties": {
                        "asin": {"type": "string"},
                        "novelty_score": {"type": "integer", "minimum": 1, "maximum": 10},
                        "reason": {"type": "string", "maxLength": 140},
                    },
                    "required": ["asin", "novelty_score", "reason"],
                },
            }
        },
        "required": ["top10"],
    },
}


class RankError(Exception):
    pass


def _truncate(s: str | None, n: int) -> str:
    if not s:
        return ""
    return s[:n]


def _build_user_message(products: list[Product]) -> str:
    lines = [
        "Here are candidate products. Pick the top "
        f"{TOP_N} most novel and submit via submit_ranking.\n"
    ]
    payload = [
        {
            "asin": p["asin"],
            "title": p["title"],
            "price": p["price"],
            "description": _truncate(p["description"], MAX_DESCRIPTION_CHARS),
        }
        for p in products
    ]
    lines.append(json.dumps(payload, indent=2))
    return "".join(lines)


def _extract_tool_input(message: Any) -> dict | None:
    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "submit_ranking":
            return getattr(block, "input", None) or {}
    return None


def rank(
    products: list[Product],
    client: Any,
    max_retries: int = 2,
) -> list[RankedProduct]:
    """Rank products by novelty using Claude. Returns top-10 RankedProducts (or fewer)."""
    if not products:
        return []

    by_asin = {p["asin"]: p for p in products}
    user_msg = _build_user_message(products)

    last_err: Exception | None = None
    for _attempt in range(max_retries):
        message = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "submit_ranking"},
            messages=[{"role": "user", "content": user_msg}],
        )
        tool_input = _extract_tool_input(message)
        if tool_input is None:
            last_err = RankError("Model did not call submit_ranking tool.")
            continue

        top10 = tool_input.get("top10", [])
        out: list[RankedProduct] = []
        for entry in top10:
            asin = entry.get("asin")
            if asin not in by_asin:
                continue
            p = by_asin[asin]
            out.append(RankedProduct(
                asin=p["asin"],
                title=p["title"],
                price=p["price"],
                image_url=p["image_url"],
                product_url=p["product_url"],
                rating=p["rating"],
                description=p["description"],
                novelty_score=int(entry.get("novelty_score", 0)),
                reason=str(entry.get("reason", ""))[:140],
            ))
            if len(out) >= TOP_N:
                break
        return out

    raise RankError(f"Ranking failed after {max_retries} attempts: {last_err}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rank.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_rank.py amazon_report/rank.py
git commit -m "feat: rank products by novelty via Claude tool call"
```

---

## Task 6: Render Module — HTML Report

**Files:**
- Create: `amazon_report/templates/report.html.j2`
- Create: `tests/test_render.py`
- Create: `amazon_report/render.py`

- [ ] **Step 1: Create the Jinja2 template `amazon_report/templates/report.html.j2`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Amazon Novelty Report — {{ generated_at }}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #fafafa; margin: 0; padding: 2rem; color: #222; }
    header { max-width: 1100px; margin: 0 auto 2rem; }
    h1 { margin: 0 0 .5rem; font-size: 1.8rem; }
    .meta { color: #666; font-size: .9rem; }
    .grid { max-width: 1100px; margin: 0 auto; display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1.5rem; }
    .card { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.08); padding: 1rem; display: flex; flex-direction: column; }
    .card img { width: 100%; height: 200px; object-fit: contain; background: #f0f0f0; border-radius: 8px; }
    .title { font-weight: 600; font-size: 1rem; margin: .75rem 0 .25rem; line-height: 1.3; min-height: 2.6em; }
    .price { color: #b12704; font-weight: 700; font-size: 1.1rem; }
    .badge { display: inline-block; background: #ffefc4; color: #7a4f00; border-radius: 999px; padding: .15rem .6rem; font-size: .8rem; font-weight: 600; margin-left: .5rem; }
    .reason { color: #444; font-size: .9rem; margin: .5rem 0 1rem; flex: 1; }
    a.btn { display: block; text-align: center; background: #ffd814; color: #111; text-decoration: none; padding: .55rem; border-radius: 8px; font-weight: 600; font-size: .9rem; }
    a.btn:hover { background: #f7ca00; }
    .empty { color: #888; max-width: 1100px; margin: 0 auto; }
  </style>
</head>
<body>
  <header>
    <h1>Amazon Novelty Report</h1>
    <div class="meta">
      Generated {{ generated_at }} · Keywords: {{ keywords | join(", ") }} · {{ candidate_count }} candidates considered
    </div>
  </header>
  {% if products %}
  <div class="grid">
    {% for p in products %}
    <div class="card">
      <img src="{{ p.image_url }}" alt="{{ p.title }}">
      <div class="title">{{ p.title }} <span class="badge">{{ p.novelty_score }}/10</span></div>
      <div class="price">${{ "%.2f"|format(p.price) }}</div>
      <div class="reason">{{ p.reason }}</div>
      <a class="btn" href="{{ p.product_url }}" target="_blank" rel="noopener">View on Amazon</a>
    </div>
    {% endfor %}
  </div>
  {% else %}
  <div class="empty">No products to display.</div>
  {% endif %}
</body>
</html>
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_render.py`:

```python
from pathlib import Path

from amazon_report.models import RankedProduct
from amazon_report.render import render


def _ranked(asin: str, title: str, score: int, reason: str) -> RankedProduct:
    return RankedProduct(
        asin=asin, title=title, price=12.34,
        image_url=f"https://img/{asin}.jpg",
        product_url=f"https://amazon.com/dp/{asin}",
        rating=4.5, description=None,
        novelty_score=score, reason=reason,
    )


def test_render_writes_file(tmp_path: Path):
    out = tmp_path / "report.html"
    render(
        ranked=[_ranked("A1", "Cat Tea Infuser", 9, "whimsical")],
        out_path=out,
        keywords=["unique gifts"],
        candidate_count=42,
        generated_at="2026-05-06 14:32",
    )
    assert out.exists()
    html = out.read_text()
    assert "<!doctype html>" in html.lower()


def test_render_includes_product_fields(tmp_path: Path):
    out = tmp_path / "report.html"
    render(
        ranked=[_ranked("A1", "Cat Tea Infuser", 9, "whimsical and feline")],
        out_path=out,
        keywords=["unique gifts"],
        candidate_count=42,
        generated_at="2026-05-06 14:32",
    )
    html = out.read_text()
    assert "Cat Tea Infuser" in html
    assert "$12.34" in html
    assert "9/10" in html
    assert "whimsical and feline" in html
    assert "https://amazon.com/dp/A1" in html
    assert "https://img/A1.jpg" in html


def test_render_includes_metadata(tmp_path: Path):
    out = tmp_path / "report.html"
    render(
        ranked=[_ranked("A1", "X", 5, "y")],
        out_path=out,
        keywords=["foo", "bar"],
        candidate_count=99,
        generated_at="2026-05-06 14:32",
    )
    html = out.read_text()
    assert "foo, bar" in html
    assert "99 candidates" in html
    assert "2026-05-06 14:32" in html


def test_render_handles_empty_list(tmp_path: Path):
    out = tmp_path / "report.html"
    render(
        ranked=[],
        out_path=out,
        keywords=["foo"],
        candidate_count=0,
        generated_at="2026-05-06 14:32",
    )
    html = out.read_text()
    assert "No products to display" in html


def test_render_creates_parent_dirs(tmp_path: Path):
    out = tmp_path / "nested" / "deep" / "report.html"
    render(
        ranked=[_ranked("A1", "X", 5, "y")],
        out_path=out,
        keywords=["foo"],
        candidate_count=1,
        generated_at="2026-05-06 14:32",
    )
    assert out.exists()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'amazon_report.render'`

- [ ] **Step 4: Implement `amazon_report/render.py`**

```python
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from amazon_report.models import RankedProduct

_env = Environment(
    loader=PackageLoader("amazon_report", "templates"),
    autoescape=select_autoescape(["html", "j2"]),
)


def render(
    ranked: list[RankedProduct],
    out_path: Path,
    keywords: list[str],
    candidate_count: int,
    generated_at: str,
) -> None:
    """Render the HTML report to out_path."""
    template = _env.get_template("report.html.j2")
    html = template.render(
        products=ranked,
        keywords=keywords,
        candidate_count=candidate_count,
        generated_at=generated_at,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_render.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add amazon_report/templates/report.html.j2 tests/test_render.py amazon_report/render.py
git commit -m "feat: render top-10 products to self-contained HTML"
```

---

## Task 7: Main / CLI Orchestration

**Files:**
- Create: `tests/test_main.py`
- Create: `amazon_report/main.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_main.py`:

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from amazon_report.models import Product, RankedProduct


def _product(asin: str) -> Product:
    return Product(
        asin=asin, title=f"T{asin}", price=9.99,
        image_url=f"https://img/{asin}.jpg",
        product_url=f"https://amazon.com/dp/{asin}",
        rating=4.0, description=None,
    )


def _ranked(asin: str) -> RankedProduct:
    return RankedProduct(
        asin=asin, title=f"T{asin}", price=9.99,
        image_url=f"https://img/{asin}.jpg",
        product_url=f"https://amazon.com/dp/{asin}",
        rating=4.0, description=None,
        novelty_score=8, reason="novel",
    )


def test_main_missing_env_var_exits_1(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["amazon-report", "gadgets"])

    from amazon_report.main import main
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "RAPIDAPI_KEY" in err or "ANTHROPIC_API_KEY" in err


def test_main_runs_pipeline_and_writes_report(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RAPIDAPI_KEY", "rk")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak")
    monkeypatch.setattr(sys, "argv", ["amazon-report", "gadgets", "kitchen"])

    fake_search = MagicMock(side_effect=[
        [_product("A1"), _product("A2")],
        [_product("A2"), _product("A3")],  # A2 is dup
    ])
    fake_rank = MagicMock(return_value=[_ranked("A1"), _ranked("A2"), _ranked("A3")])
    fake_anthropic = MagicMock()

    with patch("amazon_report.main.search", fake_search), \
         patch("amazon_report.main.rank", fake_rank), \
         patch("amazon_report.main.Anthropic", return_value=fake_anthropic):
        from amazon_report.main import main
        main()

    # search called once per keyword
    assert fake_search.call_count == 2
    # rank called once with deduped list (3 unique products)
    fake_rank.assert_called_once()
    ranked_input = fake_rank.call_args.kwargs.get("products") or fake_rank.call_args.args[0]
    asins = sorted(p["asin"] for p in ranked_input)
    assert asins == ["A1", "A2", "A3"]

    reports = list((tmp_path / "reports").glob("report-*.html"))
    assert len(reports) == 1
    html = reports[0].read_text()
    assert "TA1" in html


def test_main_zero_candidates_exits_0(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RAPIDAPI_KEY", "rk")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak")
    monkeypatch.setattr(sys, "argv", ["amazon-report", "gadgets"])

    fake_search = MagicMock(return_value=[])
    fake_rank = MagicMock()

    with patch("amazon_report.main.search", fake_search), \
         patch("amazon_report.main.rank", fake_rank), \
         patch("amazon_report.main.Anthropic"):
        from amazon_report.main import main
        main()  # should NOT raise SystemExit

    fake_rank.assert_not_called()
    out = capsys.readouterr().out
    assert "No products" in out


def test_dedup_preserves_first_occurrence():
    from amazon_report.main import _dedup_by_asin
    a1 = _product("A1")
    a1_dup = _product("A1")
    a1_dup["title"] = "DIFFERENT"
    a2 = _product("A2")
    out = _dedup_by_asin([a1, a2, a1_dup])
    assert [p["asin"] for p in out] == ["A1", "A2"]
    assert out[0]["title"] == "TA1"  # first wins
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'amazon_report.main'`

- [ ] **Step 3: Implement `amazon_report/main.py`**

```python
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from anthropic import Anthropic
from dotenv import load_dotenv

from amazon_report.fetch import search, FetchError
from amazon_report.models import Product
from amazon_report.rank import rank, RankError
from amazon_report.render import render


REQUIRED_ENV = ["RAPIDAPI_KEY", "ANTHROPIC_API_KEY"]


def _check_env() -> dict[str, str]:
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        print(
            f"Missing env var(s): {', '.join(missing)}. "
            "Copy .env.example to .env and fill in the keys.",
            file=sys.stderr,
        )
        sys.exit(1)
    return {k: os.environ[k] for k in REQUIRED_ENV}


def _dedup_by_asin(products: list[Product]) -> list[Product]:
    seen: set[str] = set()
    out: list[Product] = []
    for p in products:
        if p["asin"] in seen:
            continue
        seen.add(p["asin"])
        out.append(p)
    return out


def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="amazon-report",
        description="Find novel Amazon products under $20 and write an HTML report.",
    )
    ap.add_argument(
        "keywords",
        nargs="+",
        help="One or more search keywords (quote multi-word phrases).",
    )
    return ap


def main() -> None:
    load_dotenv()
    env = _check_env()
    args = _build_argparser().parse_args()
    keywords: list[str] = args.keywords

    print(f"Fetching candidates for {len(keywords)} keyword(s)...")
    session = requests.Session()
    candidates: list[Product] = []
    for kw in keywords:
        try:
            results = search(kw, api_key=env["RAPIDAPI_KEY"], session=session)
        except FetchError as e:
            print(f"  ! \"{kw}\" failed: {e}", file=sys.stderr)
            continue
        print(f"  - \"{kw}\": {len(results)} under $20")
        candidates.extend(results)

    candidates = _dedup_by_asin(candidates)

    if not candidates:
        print(f"No products under $20 found for keywords: {', '.join(keywords)}")
        return

    print(f"Ranking {len(candidates)} candidates with Claude...")
    client = Anthropic(api_key=env["ANTHROPIC_API_KEY"])
    try:
        ranked = rank(candidates, client=client)
    except RankError as e:
        print(f"Ranking failed: {e}", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    out_path = Path("reports") / f"report-{now.strftime('%Y-%m-%d-%H%M')}.html"
    render(
        ranked=ranked,
        out_path=out_path,
        keywords=keywords,
        candidate_count=len(candidates),
        generated_at=now.strftime("%Y-%m-%d %H:%M"),
    )
    print(f"Wrote {out_path}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: 26 passed (7 fetch parse + 4 fetch retry + 6 rank + 5 render + 4 main).

- [ ] **Step 6: Commit**

```bash
git add tests/test_main.py amazon_report/main.py
git commit -m "feat: wire CLI orchestration with env checks and dedup"
```

---

## Task 8: Manual Smoke Test

**Files:** none

- [ ] **Step 1: Set up `.env`**

```bash
cp .env.example .env
# Edit .env and fill in your real RAPIDAPI_KEY and ANTHROPIC_API_KEY
```

- [ ] **Step 2: Run end-to-end**

```bash
python -m amazon_report "unique gadgets"
```

Expected:
```
Fetching candidates for 1 keyword(s)...
  - "unique gadgets": <some number> under $20
Ranking <N> candidates with Claude...
Wrote reports/report-2026-05-06-XXXX.html
```

- [ ] **Step 3: Open the HTML report in a browser and verify**

```bash
open reports/report-*.html  # macOS
```

Verify:
- Cards render with images
- Titles, prices, novelty score badges, and one-line reasons all visible
- "View on Amazon" links open the product page in a new tab

- [ ] **Step 4: If anything is broken, file a follow-up; otherwise we're done.**

No commit for this task — it's a manual verification step.
