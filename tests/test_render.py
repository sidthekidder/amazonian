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
