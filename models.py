from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    id: int
    name: str


@dataclass(frozen=True)
class Images:
    ids: list[str]
    base_uri: str


@dataclass(frozen=True)
class IkmanAd:
    id: str
    slug: str
    title: str
    description: str
    details: str
    subtitle: str
    imgUrl: str
    images: Images
    price: str
    discount: int
    timeStamp: str
    lastBumpUpDate: str
    category: Category
