from typing import TypedDict


class Product(TypedDict):
    asin: str
    title: str
    price: float
    image_url: str
    product_url: str
    rating: float | None
    description: str | None


class RankedProduct(TypedDict):
    asin: str
    title: str
    price: float
    image_url: str
    product_url: str
    rating: float | None
    description: str | None
    novelty_score: int
    reason: str
