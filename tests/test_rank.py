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
