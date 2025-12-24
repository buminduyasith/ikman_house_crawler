from __future__ import annotations

import json
import urllib.parse
from typing import Any, Optional
import urllib.request

from models import Category, IkmanAd, Images


def fetch_house_ads(
    url: str = "https://ikman.lk/en/ads/sri-lanka/houses-for-sale",
    timeout_sec: int = 30,
) -> list[IkmanAd]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        method="GET",
    )

    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        html = resp.read().decode(charset, errors="replace")

    initial_data = _extract_window_initial_data(html)
    ads_root: Optional[dict[str, Any]] = (
        initial_data.get("serp", {}).get("ads", {}).get("data", {})
    )
    ads_list = (ads_root or {}).get("ads") or []

    if not isinstance(ads_list, list):
        raise ValueError(
            "Unexpected format: initialData.serp.ads.data.ads is not a list"
        )

    result: list[IkmanAd] = []
    for item in ads_list:
        if isinstance(item, dict):
            result.append(_map_ad(item))
    return result


def build_paged_url(url: str, page: int) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    query["page"] = [str(page)]
    new_query = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


def _extract_window_initial_data(html: str) -> dict[str, Any]:
    marker = "window.initialData"
    idx = html.find(marker)
    if idx == -1:
        raise ValueError("window.initialData not found in HTML")

    eq_idx = html.find("=", idx)
    if eq_idx == -1:
        raise ValueError("Could not find '=' after window.initialData")

    start = html.find("{", eq_idx)
    if start == -1:
        raise ValueError("Could not find '{' starting initialData JSON")

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(html)):
        ch = html[i]

        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                json_text = html[start : i + 1]
                return json.loads(json_text)

    raise ValueError("Unterminated JSON object for window.initialData")


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def _as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _map_ad(ad: dict[str, Any]) -> IkmanAd:
    images_raw = ad.get("images") or {}
    category_raw = ad.get("category") or {}

    images = Images(
        ids=[_as_str(x) for x in (images_raw.get("ids") or [])],
        base_uri=_as_str(images_raw.get("base_uri")),
    )
    category = Category(
        id=_as_int(category_raw.get("id")),
        name=_as_str(category_raw.get("name")),
    )

    return IkmanAd(
        id=_as_str(ad.get("id")),
        slug=_as_str(ad.get("slug")),
        title=_as_str(ad.get("title")),
        description=_as_str(ad.get("description")),
        details=_as_str(ad.get("details")),
        subtitle=_as_str(ad.get("subtitle")),
        imgUrl=_as_str(ad.get("imgUrl")),
        images=images,
        price=_as_str(ad.get("price")),
        discount=_as_int(ad.get("discount")),
        timeStamp=_as_str(ad.get("timeStamp")),
        lastBumpUpDate=_as_str(ad.get("lastBumpUpDate")),
        category=category,
    )
