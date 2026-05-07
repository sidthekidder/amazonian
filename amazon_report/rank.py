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
