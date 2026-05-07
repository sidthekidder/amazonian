import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from anthropic import Anthropic
from dotenv import load_dotenv
from flask import Flask, render_template, request

from amazon_report.fetch import (
    DEFAULT_MAX_PRICE,
    DEFAULT_MIN_PRICE,
    FetchError,
    search,
)
from amazon_report.models import Product
from amazon_report.rank import RankError, rank


REQUIRED_ENV = ["RAPIDAPI_KEY", "ANTHROPIC_API_KEY"]


def _dedup_by_asin(products: list[Product]) -> list[Product]:
    seen: set[str] = set()
    out: list[Product] = []
    for p in products:
        if p["asin"] in seen:
            continue
        seen.add(p["asin"])
        out.append(p)
    return out


def _render(
    *,
    keywords_raw: str,
    min_price: float,
    max_price: float,
    products: list | None = None,
    candidate_count: int = 0,
    error: str | None = None,
    generated_at: str | None = None,
):
    return render_template(
        "web.html.j2",
        keywords_raw=keywords_raw,
        min_price=min_price,
        max_price=max_price,
        products=products,
        candidate_count=candidate_count,
        error=error,
        generated_at=generated_at,
    )


def create_app() -> Flask:
    load_dotenv(dotenv_path=Path(".env"))
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        print(
            f"Missing env var(s): {', '.join(missing)}. "
            "Copy .env.example to .env and fill in the keys.",
            file=sys.stderr,
        )
        sys.exit(1)

    app = Flask(__name__, template_folder="templates")

    @app.get("/")
    def index():
        return _render(
            keywords_raw="",
            min_price=DEFAULT_MIN_PRICE,
            max_price=DEFAULT_MAX_PRICE,
        )

    @app.post("/")
    def do_search():
        keywords_raw = (request.form.get("keywords") or "").strip()
        min_price_raw = (request.form.get("min_price") or "").strip()
        max_price_raw = (request.form.get("max_price") or "").strip()

        try:
            min_price = float(min_price_raw) if min_price_raw else DEFAULT_MIN_PRICE
            max_price = float(max_price_raw) if max_price_raw else DEFAULT_MAX_PRICE
        except ValueError:
            return _render(
                keywords_raw=keywords_raw,
                min_price=DEFAULT_MIN_PRICE,
                max_price=DEFAULT_MAX_PRICE,
                error="Min and max price must be numeric.",
            )

        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
        if not keywords:
            return _render(
                keywords_raw=keywords_raw,
                min_price=min_price,
                max_price=max_price,
                error="Enter at least one keyword.",
            )
        if min_price < 0 or max_price <= 0:
            return _render(
                keywords_raw=keywords_raw,
                min_price=min_price,
                max_price=max_price,
                error="Prices must be non-negative (max must be > 0).",
            )
        if min_price >= max_price:
            return _render(
                keywords_raw=keywords_raw,
                min_price=min_price,
                max_price=max_price,
                error=f"Min price ({min_price:g}) must be less than max price ({max_price:g}).",
            )

        api_key = os.environ["RAPIDAPI_KEY"]
        session = requests.Session()
        candidates: list[Product] = []
        fetch_errors: list[str] = []
        for kw in keywords:
            try:
                results = search(
                    kw,
                    api_key=api_key,
                    session=session,
                    max_price=max_price,
                    min_price=min_price,
                )
            except FetchError as e:
                fetch_errors.append(f'"{kw}": {e}')
                continue
            candidates.extend(results)
        candidates = _dedup_by_asin(candidates)

        if not candidates:
            msg = "No products found in this range."
            if fetch_errors:
                msg += " (" + "; ".join(fetch_errors) + ")"
            return _render(
                keywords_raw=keywords_raw,
                min_price=min_price,
                max_price=max_price,
                products=[],
                error=msg,
            )

        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        try:
            ranked = rank(candidates, client=client)
        except RankError as e:
            return _render(
                keywords_raw=keywords_raw,
                min_price=min_price,
                max_price=max_price,
                error=f"Ranking failed: {e}",
            )

        return _render(
            keywords_raw=keywords_raw,
            min_price=min_price,
            max_price=max_price,
            products=ranked,
            candidate_count=len(candidates),
            error="; ".join(fetch_errors) if fetch_errors else None,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

    return app


def run() -> None:
    app = create_app()
    port = int(os.environ.get("PORT", "8000"))
    print(f"Open http://127.0.0.1:{port}/ in your browser.")
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    run()
