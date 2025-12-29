from __future__ import annotations

import json
import os
from typing import Optional

import gspread
from gspread import Spreadsheet, Worksheet


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


def load_sent_ids(sheet_id: str) -> set[str]:
    """Load sent ad IDs from Google Sheet column A."""
    sheet = _get_sheet(sheet_id)
    if not sheet:
        return set()

    try:
        values = sheet.col_values(1)
        return set(v for v in values if v)
    except Exception:
        return set()


def save_sent_ids(ad_ids: list[str], sheet_id: str) -> bool:
    """Append new ad IDs to Google Sheet column A."""
    if not ad_ids:
        return True

    sheet = _get_sheet(sheet_id)
    if not sheet:
        return False

    try:
        rows = [[ad_id] for ad_id in ad_ids]
        sheet.append_rows(rows, value_input_option="RAW")
        return True
    except Exception:
        return False


def filter_unsent_ads(ads: list, sent_ids: set[str]) -> list:
    """Return only ads that haven't been sent yet."""
    return [ad for ad in ads if ad.id and ad.id not in sent_ids]
