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
