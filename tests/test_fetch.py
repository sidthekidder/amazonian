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
