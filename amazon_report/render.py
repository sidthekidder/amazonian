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
