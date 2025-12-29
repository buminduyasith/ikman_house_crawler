from __future__ import annotations

import logging
import os
import urllib.error
import urllib.parse
import re
from typing import Optional

from house_crawler import build_paged_url, fetch_house_ads
from telegram_sender import send_ads_media_groups
from sheets_tracker import load_sent_ids, save_sent_ids, filter_unsent_ads


def _parse_price_lkr(price_text: str) -> Optional[int]:
    digits = "".join(ch for ch in (price_text or "") if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _get_optional_int(name: str) -> Optional[int]:
    value = os.getenv(name)
    if not value:
        return None
    return int(value)


def _is_truthy_env(name: str) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _parse_districts(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",")]
    districts: list[str] = []
    for p in parts:
        if not p:
            continue
        districts.append(p.lower().replace(" ", "-"))
    return districts


def _parse_int_from_details(details: str, label: str) -> Optional[int]:
    if not details:
        return None
    match = re.search(rf"\b{re.escape(label)}\s*:\s*(\d+)\b", details, re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _with_district_in_path(url: str, district: str) -> str:
    parsed = urllib.parse.urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]

    try:
        ads_idx = segments.index("ads")
    except ValueError:
        raise ValueError(f"IKMAN_URL path does not contain '/ads/': {url}")

    if ads_idx + 1 >= len(segments):
        raise ValueError(f"IKMAN_URL path missing location after '/ads/': {url}")

    segments[ads_idx + 1] = district
    new_path = "/" + "/".join(segments)
    return urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            new_path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def main() -> None:
    _load_dotenv()

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
    logger = logging.getLogger("ikman_house_crawler")

    bot_token = _get_required_env("TELEGRAM_BOT_TOKEN")
    chat_id = _get_required_env("TELEGRAM_CHAT_ID")
    ikman_url = os.getenv(
        "IKMAN_URL", "https://ikman.lk/en/ads/sri-lanka/houses-for-sale"
    )
    districts = _parse_districts(os.getenv("DISTRICTS"))
    limit = _get_optional_int("SEND_LIMIT")
    max_images = _get_optional_int("MAX_IMAGES") or 10
    pages = _get_optional_int("PAGES") or 1
    start_page = _get_optional_int("START_PAGE") or 1
    price_min = _get_optional_int("PRICE_MIN")
    price_max = _get_optional_int("PRICE_MAX")
    bedrooms_min = _get_optional_int("BEDROOMS_MIN")
    bathrooms_min = _get_optional_int("BATHROOMS_MIN")
    brand_new_only = _is_truthy_env("BRAND_NEW_ONLY")

    all_ads = []
    seen_ids: set[str] = set()

    if districts:
        logger.info("Fetching ads from base: %s", ikman_url)
        logger.info("Districts: %s", ",".join(districts))
    else:
        logger.info("Fetching ads from: %s", ikman_url)

    logger.info("Pagination: start_page=%s pages=%s", start_page, pages)

    target_urls: list[tuple[str, str]] = []
    if districts:
        for d in districts:
            target_urls.append((d, _with_district_in_path(ikman_url, d)))
    else:
        target_urls.append(("", ikman_url))

    for district, district_url in target_urls:
        for page in range(start_page, start_page + pages):
            page_url = build_paged_url(district_url, page)
            if district:
                logger.info(
                    "Fetching district=%s page=%s: %s", district, page, page_url
                )
            else:
                logger.info("Fetching page %s: %s", page, page_url)

            try:
                page_ads = fetch_house_ads(url=page_url)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    if district:
                        logger.warning(
                            "Invalid district slug '%s' (HTTP 404). Please fix/remove it in DISTRICTS. URL: %s",
                            district,
                            page_url,
                        )
                    else:
                        logger.warning(
                            "HTTP 404 while fetching URL (check IKMAN_URL path): %s",
                            page_url,
                        )
                    break
                raise
            if district:
                logger.info(
                    "Fetched %s ads from district=%s page=%s",
                    len(page_ads),
                    district,
                    page,
                )
            else:
                logger.info("Fetched %s ads from page %s", len(page_ads), page)

            for ad in page_ads:
                if ad.id and ad.id not in seen_ids:
                    seen_ids.add(ad.id)
                    all_ads.append(ad)

    ads = all_ads
    logger.info("Total unique ads fetched: %s", len(ads))

    if price_min is not None:
        before = len(ads)
        ads = [
            ad
            for ad in ads
            if (parsed := _parse_price_lkr(ad.price)) is not None
            and parsed >= price_min
        ]
        logger.info(
            "Price filter PRICE_MIN=%s PRICE_MAX=%s kept %s/%s ads",
            price_min,
            price_max,
            len(ads),
            before,
        )

    if bedrooms_min is not None or bathrooms_min is not None:
        before = len(ads)

        def _keep(ad) -> bool:  # type: ignore[no-redef]
            bedrooms = _parse_int_from_details(ad.details, "Bedrooms")
            bathrooms = _parse_int_from_details(ad.details, "Bathrooms")
            if bedrooms_min is not None and (
                bedrooms is None or bedrooms < bedrooms_min
            ):
                return False
            if bathrooms_min is not None and (
                bathrooms is None or bathrooms < bathrooms_min
            ):
                return False
            return True

        ads = [ad for ad in ads if _keep(ad)]
        logger.info(
            "Details filter BEDROOMS_MIN=%s BATHROOMS_MIN=%s kept %s/%s ads",
            bedrooms_min,
            bathrooms_min,
            len(ads),
            before,
        )

    if brand_new_only:
        before = len(ads)
        ads = [
            ad
            for ad in ads
            if ad.title
            and re.search(r"\bbrand\s*[- ]\s*new\b", ad.title, re.IGNORECASE)
        ]
        logger.info(
            "Title filter BRAND_NEW_ONLY=%s kept %s/%s ads",
            brand_new_only,
            len(ads),
            before,
        )

    if price_max is not None:
        before = len(ads)
        ads = [
            ad
            for ad in ads
            if (parsed := _parse_price_lkr(ad.price)) is not None
            and parsed <= price_max
        ]
        logger.info(
            "Price filter PRICE_MIN=%s PRICE_MAX=%s kept %s/%s ads",
            price_min,
            price_max,
            len(ads),
            before,
        )

    if not ads:
        logger.info("No ads found, nothing to send")
        return

    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if sheet_id:
        sent_ids = load_sent_ids(sheet_id)
        logger.info("Loaded %s previously sent ad IDs from Google Sheet", len(sent_ids))

        unsent_ads = filter_unsent_ads(ads, sent_ids)
        logger.info(
            "Found %s new ads (filtered out %s already sent)",
            len(unsent_ads),
            len(ads) - len(unsent_ads),
        )

        if not unsent_ads:
            logger.info("All ads have already been sent, nothing new to send")
            return

        ads_to_send = unsent_ads
    else:
        logger.info("GOOGLE_SHEET_ID not set, skipping duplicate check")
        ads_to_send = ads

    logger.info(
        "Sending ads to Telegram chat_id=%s (limit=%s, max_images=%s)",
        chat_id,
        limit,
        max_images,
    )
    send_ads_media_groups(
        bot_token=bot_token,
        chat_id=chat_id,
        ads=ads_to_send,
        limit=limit,
        max_images=max_images,
        logger=logger,
    )

    if sheet_id:
        sent_ad_ids = (
            [ad.id for ad in ads_to_send[:limit] if ad.id]
            if limit
            else [ad.id for ad in ads_to_send if ad.id]
        )
        if save_sent_ids(sent_ad_ids, sheet_id):
            logger.info("Saved %s new ad IDs to Google Sheet", len(sent_ad_ids))
        else:
            logger.warning("Failed to save ad IDs to Google Sheet")

    logger.info("Done")


if __name__ == "__main__":
    main()
