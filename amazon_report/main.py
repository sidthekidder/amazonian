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
    load_dotenv(dotenv_path=Path(".env"))
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
