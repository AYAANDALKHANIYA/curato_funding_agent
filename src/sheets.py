"""
src/sheets.py
-------------
Writes lead data to Google Sheets (via gspread) or a local CSV fallback.
"""

import csv
import logging
import os
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sheet configuration
# ---------------------------------------------------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_HEADERS = [
    "Company Name",
    "Website",
    "LinkedIn",
    "Location",
    "Industry",
    "Company Stage",
    "Announcement Type",
    "Funding/Grant Amount",
    "Announcement Date",
    "Source URL",
    "Lead Score",
    "Why This Lead?",
    "Source Name",
    "Collected At",
]

# Mapping: SHEET_HEADERS label → lead dict key
_HEADER_TO_KEY = {
    "Company Name": "company_name",
    "Website": "website_url",
    "LinkedIn": "linkedin_url",
    "Location": "location",
    "Industry": "industry",
    "Company Stage": "company_stage",
    "Announcement Type": "announcement_type",
    "Funding/Grant Amount": "funding_amount",
    "Announcement Date": "announcement_date",
    "Source URL": "source_url",
    "Lead Score": "lead_score",
    "Why This Lead?": "why_this_lead",
    "Source Name": "source_name",
    "Collected At": None,  # generated at write time
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_client() -> gspread.Client:
    """Authenticate with the Google Service Account and return a gspread client."""
    json_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
    if not os.path.isabs(json_path):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        json_path = os.path.join(base, json_path)

    creds = Credentials.from_service_account_file(json_path, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client


def _ensure_headers(worksheet: gspread.Worksheet) -> None:
    """Write SHEET_HEADERS into row 1 if it is currently empty."""
    try:
        row1 = worksheet.row_values(1)
        if not any(row1):
            worksheet.insert_row(SHEET_HEADERS, index=1)
            logger.info("Headers written to sheet.")
    except Exception as exc:
        logger.error("Failed to ensure headers: %s", exc)


def _lead_to_row(lead: dict) -> list:
    """Convert a lead dict to an ordered list matching SHEET_HEADERS."""
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    row = []
    for header in SHEET_HEADERS:
        if header == "Collected At":
            row.append(now_str)
        else:
            key = _HEADER_TO_KEY.get(header)
            value = lead.get(key, "") if key else ""
            row.append("" if value is None else str(value))
    return row


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def write_leads_to_sheet(leads: list) -> int:
    """
    Write leads to the Google Sheet, into a tab named by current month.

    Args:
        leads: list of scored lead dicts

    Returns:
        Number of rows written.
    """
    if not leads:
        logger.info("No leads to write to sheet.")
        return 0

    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "")
    if not sheet_id:
        raise ValueError("GOOGLE_SHEET_ID is not set in environment.")

    try:
        client = _get_client()
        spreadsheet = client.open_by_key(sheet_id)
    except Exception as exc:
        logger.error("Failed to open Google Sheet: %s", exc)
        raise

    # Tab named by current month e.g. "June 2025"
    tab_name = datetime.utcnow().strftime("%B %Y")

    try:
        worksheet = spreadsheet.worksheet(tab_name)
        logger.info("Found existing worksheet: %s", tab_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=tab_name, rows=5000, cols=len(SHEET_HEADERS))
        logger.info("Created new worksheet: %s", tab_name)

    _ensure_headers(worksheet)

    rows = [_lead_to_row(lead) for lead in leads]

    try:
        worksheet.append_rows(rows, value_input_option="USER_ENTERED")
        logger.info("Wrote %d rows to sheet tab '%s'.", len(rows), tab_name)
    except Exception as exc:
        logger.error("Failed to append rows to sheet: %s", exc)
        raise

    return len(rows)


def write_leads_to_csv_fallback(leads: list, path: str = None) -> int:
    """
    Append leads to a local CSV file (used when Google Sheets is not configured).

    Args:
        leads: list of scored lead dicts
        path:  output CSV path (default: data/leads_output.csv)

    Returns:
        Number of rows written.
    """
    if not leads:
        logger.info("No leads to write to CSV.")
        return 0

    if path is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, "data", "leads_output.csv")

    os.makedirs(os.path.dirname(path), exist_ok=True)

    file_exists = os.path.isfile(path)

    # Build fieldnames from _HEADER_TO_KEY mapping
    fieldnames = [_HEADER_TO_KEY.get(h) or "collected_at" for h in SHEET_HEADERS]
    # Replace None-keyed header
    fieldnames = [f if f != "collected_at" else "collected_at" for f in fieldnames]

    with open(path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SHEET_HEADERS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()

        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        for lead in leads:
            row = {header: "" for header in SHEET_HEADERS}
            for header in SHEET_HEADERS:
                if header == "Collected At":
                    row[header] = now_str
                else:
                    key = _HEADER_TO_KEY.get(header)
                    value = lead.get(key, "") if key else ""
                    row[header] = "" if value is None else str(value)
            writer.writerow(row)

    logger.info("Wrote %d leads to CSV: %s", len(leads), path)
    return len(leads)
