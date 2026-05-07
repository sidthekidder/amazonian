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


def test_parse_search_response_respects_custom_max_price():
    # cap at $10 — only $8.50 item survives
    products = parse_search_response(FIXTURE, max_price=10.0)
    asins = [p["asin"] for p in products]
    assert asins == ["B0AAA00002"]


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
    assert calls[2] == {"min": 100.0, "max": 200.0, "sort": "HIGHEST_PRICE"}


def test_multi_search_skips_mid_for_tight_range(monkeypatch):
    calls: list[dict] = []

    def fake_search(keyword, api_key, session=None, max_price=20.0, min_price=0.0, sort_by="HIGHEST_PRICE"):
        calls.append({"min": min_price, "max": max_price, "sort": sort_by})
        return []

    monkeypatch.setattr("amazon_report.fetch.search", fake_search)
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
    assert len(out) == 3 * PER_CALL_CAP
    asins = {p["asin"] for p in out}
    assert "A0" in asins and "A9" in asins and "A10" not in asins
    assert "B0" in asins and "B9" in asins and "B10" not in asins
    assert "C0" in asins and "C9" in asins and "C10" not in asins


def test_multi_search_dedups_by_asin(monkeypatch):
    high = [_product("X1", 250.0), _product("X2", 240.0)]
    low = [_product("X3", 5.0), _product("X1", 250.0)]
    mid = [_product("X4", 150.0), _product("X2", 240.0)]
    queue = [high, low, mid]

    def fake_search(*args, **kwargs):
        return queue.pop(0)

    monkeypatch.setattr("amazon_report.fetch.search", fake_search)
    out = multi_search("widgets", api_key="k", min_price=0.0, max_price=300.0)
    asins = [p["asin"] for p in out]
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
