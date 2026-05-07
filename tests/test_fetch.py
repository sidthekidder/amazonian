import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from amazon_report.fetch import parse_search_response, _parse_price, search, FetchError


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
