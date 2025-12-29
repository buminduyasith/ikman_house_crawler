from __future__ import annotations

import json
import logging
import socket
import time
import urllib.request
from typing import Optional

from models import IkmanAd


class TelegramSendError(RuntimeError):
    pass


def _normalize_bot_token(bot_token: str) -> str:
    token = (bot_token or "").strip()
    if token.startswith("bot"):
        token = token[3:]
    return token


def _http_error_details(e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            body = ""
        suffix = f"\nResponse body: {body[:500]}" if body else ""
        return f"HTTP Error {e.code}: {e.reason} ({e.geturl()}){suffix}"
    return str(e)


def _parse_retry_after_seconds(body: str) -> Optional[int]:
    if not body:
        return None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None
    params = parsed.get("parameters") or {}
    retry_after = params.get("retry_after")
    if isinstance(retry_after, int) and retry_after > 0:
        return retry_after
    return None


def _escape_markdown(text: str) -> str:
    if not text:
        return text
    escaped = text
    for ch in ("_", "*", "`", "["):
        escaped = escaped.replace(ch, f"\\{ch}")
    return escaped


def _build_ad_message(ad: IkmanAd) -> str:
    ad_url = f"https://ikman.lk/en/ad/{ad.slug}"
    parts = [
        ad.title,
        ad.price,
        ad.description,
        ad.details,
        ad_url,
    ]
    return "\n".join([p for p in parts if p])


def _build_ad_caption_markdown(ad: IkmanAd, max_length: int = 1024) -> str:
    lines = []
    if ad.title:
        lines.append(f"*{_escape_markdown(ad.title)}*")
    if ad.price:
        lines.append(_escape_markdown(ad.price))
    if ad.description:
        desc = (
            ad.description[:200] + "..."
            if len(ad.description) > 200
            else ad.description
        )
        lines.append(_escape_markdown(desc))
    if ad.details:
        lines.append(_escape_markdown(ad.details))
    if ad.slug:
        lines.append(f"https://ikman.lk/en/ad/{ad.slug}")
    caption = "\n".join(lines)
    if len(caption) > max_length:
        caption = caption[: max_length - 3] + "..."
    return caption


def _ad_image_urls(ad: IkmanAd, max_images: int = 10) -> list[str]:
    urls: list[str] = []

    if ad.imgUrl:
        urls.append(ad.imgUrl)

    base_uri = getattr(ad.images, "base_uri", "")
    ids = getattr(ad.images, "ids", [])
    if base_uri and ids:
        for image_id in ids:
            if len(urls) >= max_images:
                break
            url = f"{base_uri}/{ad.slug}/{image_id}/620/466/fitted.jpg"
            if url not in urls:
                urls.append(url)

    return urls[:max_images]


def send_media_group(
    *,
    bot_token: str,
    chat_id: str,
    media: list[dict],
) -> dict:
    token = _normalize_bot_token(bot_token)
    url = f"https://api.telegram.org/bot{token}/sendMediaGroup"

    payload = {
        "chat_id": chat_id,
        "media": media,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    last_error: Optional[Exception] = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            last_error = None
            break
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                err_body = ""

            if e.code == 429:
                retry_after = _parse_retry_after_seconds(err_body) or 5
                if attempt < 4:
                    time.sleep(retry_after + 1)
                    last_error = e
                    continue
            if e.code == 400:
                raise TelegramSendError(
                    f"Bad Request (400): {err_body[:500]}. Check image URLs or caption length."
                ) from e
            raise TelegramSendError(_http_error_details(e)) from e
        except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
            if attempt < 4:
                delay_sec = 2**attempt
                time.sleep(delay_sec)
                last_error = e
                continue
            raise TelegramSendError(_http_error_details(e)) from e
        except Exception as e:  # noqa: BLE001
            raise TelegramSendError(_http_error_details(e)) from e

    if last_error is not None:
        raise TelegramSendError(_http_error_details(last_error)) from last_error

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        raise TelegramSendError(f"Invalid JSON response: {body[:300]}") from e

    if not parsed.get("ok"):
        raise TelegramSendError(f"Telegram API error: {parsed}")

    return parsed


def send_ad_media_group(
    *,
    bot_token: str,
    chat_id: str,
    ad: IkmanAd,
    max_images: int = 10,
) -> dict:
    urls = _ad_image_urls(ad, max_images=max_images)
    if not urls:
        return send_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=_build_ad_message(ad),
            disable_web_page_preview=True,
        )

    caption = _build_ad_caption_markdown(ad)

    media: list[dict] = []
    for idx, url in enumerate(urls):
        item: dict = {"type": "photo", "media": url}
        if idx == 0 and caption:
            item["caption"] = caption
            item["parse_mode"] = "Markdown"
        media.append(item)

    return send_media_group(bot_token=bot_token, chat_id=chat_id, media=media)


def send_ads_media_groups(
    *,
    bot_token: str,
    chat_id: str,
    ads: list[IkmanAd],
    limit: Optional[int] = None,
    max_images: int = 10,
    logger: Optional[logging.Logger] = None,
) -> list[dict]:
    results: list[dict] = []
    count = 0
    for ad in ads:
        if limit is not None and count >= limit:
            break
        if logger is not None:
            logger.info(
                "Sending %s/%s: %s",
                count + 1,
                limit if limit is not None else len(ads),
                ad.title,
            )
        results.append(
            send_ad_media_group(
                bot_token=bot_token,
                chat_id=chat_id,
                ad=ad,
                max_images=max_images,
            )
        )
        if logger is not None:
            logger.info("Sent: %s", ad.slug)
        count += 1
    return results


def send_message(
    *,
    bot_token: str,
    chat_id: str,
    text: str,
    disable_web_page_preview: bool = False,
) -> dict:
    token = _normalize_bot_token(bot_token)
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": disable_web_page_preview,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    last_error: Optional[Exception] = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            last_error = None
            break
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                err_body = ""

            if e.code == 429:
                retry_after = _parse_retry_after_seconds(err_body) or 5
                if attempt < 4:
                    time.sleep(retry_after + 1)
                    last_error = e
                    continue
            raise TelegramSendError(_http_error_details(e)) from e
        except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
            if attempt < 4:
                delay_sec = 2**attempt
                time.sleep(delay_sec)
                last_error = e
                continue
            raise TelegramSendError(_http_error_details(e)) from e
        except Exception as e:  # noqa: BLE001
            raise TelegramSendError(_http_error_details(e)) from e

    if last_error is not None:
        raise TelegramSendError(_http_error_details(last_error)) from last_error

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        raise TelegramSendError(f"Invalid JSON response: {body[:300]}") from e

    if not parsed.get("ok"):
        raise TelegramSendError(f"Telegram API error: {parsed}")

    return parsed


def send_ad(
    *,
    bot_token: str,
    chat_id: str,
    ad: IkmanAd,
    disable_web_page_preview: bool = False,
) -> dict:
    return send_message(
        bot_token=bot_token,
        chat_id=chat_id,
        text=_build_ad_message(ad),
        disable_web_page_preview=disable_web_page_preview,
    )


def send_ads(
    *,
    bot_token: str,
    chat_id: str,
    ads: list[IkmanAd],
    limit: Optional[int] = None,
    disable_web_page_preview: bool = False,
) -> list[dict]:
    results: list[dict] = []
    count = 0
    for ad in ads:
        if limit is not None and count >= limit:
            break
        results.append(
            send_ad(
                bot_token=bot_token,
                chat_id=chat_id,
                ad=ad,
                disable_web_page_preview=disable_web_page_preview,
            )
        )
        count += 1
    return results
