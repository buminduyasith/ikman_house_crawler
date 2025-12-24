from __future__ import annotations

import logging
import os
from typing import Optional

from house_crawler import build_paged_url, fetch_house_ads
from telegram_sender import send_ads_media_groups


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
    limit = _get_optional_int("SEND_LIMIT")
    max_images = _get_optional_int("MAX_IMAGES") or 10
    pages = _get_optional_int("PAGES") or 1
    start_page = _get_optional_int("START_PAGE") or 1
    price_max = _get_optional_int("PRICE_MAX")

    all_ads = []
    seen_ids: set[str] = set()
    logger.info("Fetching ads from: %s", ikman_url)
    logger.info("Pagination: start_page=%s pages=%s", start_page, pages)
    for page in range(start_page, start_page + pages):
        page_url = build_paged_url(ikman_url, page)
        logger.info("Fetching page %s: %s", page, page_url)
        page_ads = fetch_house_ads(url=page_url)
        logger.info("Fetched %s ads from page %s", len(page_ads), page)

        for ad in page_ads:
            if ad.id and ad.id not in seen_ids:
                seen_ids.add(ad.id)
                all_ads.append(ad)

    ads = all_ads
    logger.info("Total unique ads fetched: %s", len(ads))

    if price_max is not None:
        before = len(ads)
        ads = [
            ad
            for ad in ads
            if (parsed := _parse_price_lkr(ad.price)) is not None
            and parsed <= price_max
        ]
        logger.info(
            "Price filter PRICE_MAX=%s kept %s/%s ads", price_max, len(ads), before
        )

    if not ads:
        logger.info("No ads found, nothing to send")
        return

    logger.info(
        "Sending ads to Telegram chat_id=%s (limit=%s, max_images=%s)",
        chat_id,
        limit,
        max_images,
    )
    send_ads_media_groups(
        bot_token=bot_token,
        chat_id=chat_id,
        ads=ads,
        limit=limit,
        max_images=max_images,
        logger=logger,
    )

    logger.info("Done")


if __name__ == "__main__":
    main()
