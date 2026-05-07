import time
from typing import Any

import requests

from amazon_report.models import Product

RAPIDAPI_HOST = "real-time-amazon-data.p.rapidapi.com"
SEARCH_URL = f"https://{RAPIDAPI_HOST}/search"
DEFAULT_MAX_PRICE = 20.0
DEFAULT_MIN_PRICE = 0.0
RETRIES = 3
BACKOFF_BASE = 1.0


class FetchError(Exception):
    pass


def _parse_price(raw: Any) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = s.replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _parse_rating(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def parse_search_response(
    payload: dict[str, Any],
    max_price: float = DEFAULT_MAX_PRICE,
    min_price: float = DEFAULT_MIN_PRICE,
) -> list[Product]:
    """Pure function: take RapidAPI JSON, return Products in [min_price, max_price)."""
    items = payload.get("data", {}).get("products", []) or []
    out: list[Product] = []
    for item in items:
        price = _parse_price(item.get("product_price"))
        if price is None or price >= max_price or price < min_price:
            continue
        asin = item.get("asin")
        title = item.get("product_title")
        image_url = item.get("product_photo")
        product_url = item.get("product_url")
        if not (asin and title and image_url and product_url):
            continue
        out.append(Product(
            asin=asin,
            title=title,
            price=price,
            image_url=image_url,
            product_url=product_url,
            rating=_parse_rating(item.get("product_star_rating")),
            description=item.get("product_description"),
        ))
    return out


def search(
    keyword: str,
    api_key: str,
    session: requests.Session | None = None,
    max_price: float = DEFAULT_MAX_PRICE,
    min_price: float = DEFAULT_MIN_PRICE,
    sort_by: str = "HIGHEST_PRICE",
) -> list[Product]:
    """Search RapidAPI and return parsed products in [min_price, max_price). Retries on 429/5xx."""
    sess = session or requests.Session()
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }
    params: dict[str, Any] = {
        "query": keyword,
        "country": "US",
        "sort_by": sort_by,
    }
    if min_price > 0:
        params["min_price"] = str(min_price)
    if max_price > 0:
        params["max_price"] = str(max_price)
    last_err: Exception | None = None
    for attempt in range(RETRIES):
        try:
            resp = sess.get(SEARCH_URL, headers=headers, params=params, timeout=20)
            if resp.status_code in (401, 403):
                raise FetchError(
                    f"RapidAPI auth failed ({resp.status_code}). Check RAPIDAPI_KEY."
                )
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                last_err = FetchError(f"RapidAPI {resp.status_code}: {resp.text[:200]}")
                time.sleep(BACKOFF_BASE * (2 ** attempt))
                continue
            resp.raise_for_status()
            return parse_search_response(
                resp.json(), max_price=max_price, min_price=min_price
            )
        except requests.RequestException as e:
            last_err = e
            time.sleep(BACKOFF_BASE * (2 ** attempt))
    raise FetchError(f"RapidAPI request failed after {RETRIES} retries: {last_err}")
