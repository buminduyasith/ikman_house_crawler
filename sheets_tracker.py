from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional, Any

import gspread
from gspread import Spreadsheet, Worksheet


HEADER_ROW = ["ID", "Title", "Price", "Details", "Link", "Status", "Sent At"]


def _get_credentials_dict() -> Optional[dict]:
    """Get credentials from environment variable (JSON string)."""
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_json:
        return None
    try:
        return json.loads(creds_json)
    except json.JSONDecodeError:
        return None


def _get_sheet(sheet_id: str) -> Optional[Worksheet]:
    """Connect to Google Sheets and return the first worksheet."""
    creds = _get_credentials_dict()
    if not creds:
        return None

    try:
        gc = gspread.service_account_from_dict(creds)
        spreadsheet: Spreadsheet = gc.open_by_key(sheet_id)
        return spreadsheet.sheet1
    except Exception:
        return None


def ensure_headers(sheet_id: str) -> bool:
    """Ensure the sheet has headers in the first row."""
    sheet = _get_sheet(sheet_id)
    if not sheet:
        return False

    try:
        first_row = sheet.row_values(1)
        if not first_row or first_row[0] != "ID":
            sheet.insert_row(HEADER_ROW, 1)
        return True
    except Exception:
        return False


def load_sent_ids(sheet_id: str) -> set[str]:
    """Load sent ad IDs from Google Sheet column A (skipping header)."""
    sheet = _get_sheet(sheet_id)
    if not sheet:
        return set()

    try:
        values = sheet.col_values(1)
        return set(v for v in values[1:] if v)
    except Exception:
        return set()


def save_ad_to_sheet(ad: Any, sheet_id: str) -> bool:
    """Save a single ad with full details to Google Sheet."""
    sheet = _get_sheet(sheet_id)
    if not sheet:
        return False

    try:
        link = f"https://ikman.lk/en/ad/{ad.slug}" if ad.slug else ""
        sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        row = [
            ad.id or "",
            ad.title or "",
            ad.price or "",
            ad.details or "",
            link,
            "Sent",
            sent_at,
        ]
        sheet.append_row(row, value_input_option="RAW")
        return True
    except Exception:
        return False


def save_ads_batch_to_sheet(ads: list[Any], sheet_id: str) -> bool:
    """Save multiple ads with full details to Google Sheet in one API call."""
    if not ads:
        return True

    sheet = _get_sheet(sheet_id)
    if not sheet:
        return False

    try:
        sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        for ad in ads:
            link = f"https://ikman.lk/en/ad/{ad.slug}" if ad.slug else ""
            rows.append(
                [
                    ad.id or "",
                    ad.title or "",
                    ad.price or "",
                    ad.details or "",
                    link,
                    "Sent",
                    sent_at,
                ]
            )
        sheet.append_rows(rows, value_input_option="RAW")
        return True
    except Exception:
        return False


def filter_unsent_ads(ads: list, sent_ids: set[str]) -> list:
    """Return only ads that haven't been sent yet."""
    return [ad for ad in ads if ad.id and ad.id not in sent_ids]
