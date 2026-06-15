"""
src/deduplicator.py
--------------------
SQLite-based deduplication of leads.
Uses a SHA-256 hash of (company_name_lowercase|announcement_date) as the unique key.
"""

import hashlib
import logging
import os
import sqlite3
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_DIR = os.path.join(_BASE_DIR, "data")
_DB_PATH = os.path.join(_DB_DIR, "seen_leads.db")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS seen_leads (
    hash TEXT PRIMARY KEY,
    company_name TEXT,
    announcement_date TEXT,
    created_at TEXT
)
"""


def _get_connection() -> sqlite3.Connection:
    """Ensure data/ directory exists and return a DB connection."""
    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(_CREATE_TABLE_SQL)
    conn.commit()
    return conn


def _make_hash(lead: dict) -> str:
    """
    Compute a SHA-256 fingerprint for a lead.
    Key: "{company_name_lowercase}|{announcement_date}"
    """
    company = (lead.get("company_name") or "").lower().strip()
    date = (lead.get("announcement_date") or "").strip()
    raw = f"{company}|{date}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def remove_duplicates(leads: list) -> list:
    """
    Filter out leads already seen (in-batch or in the persistent DB).

    Steps:
      1. Compute hash for each lead.
      2. Deduplicate within the current batch.
      3. Check each remaining hash against the DB.
      4. Insert new hashes into the DB.
      5. Log how many leads were dropped.

    Args:
        leads: list of lead dicts

    Returns:
        list of unique (previously unseen) lead dicts
    """
    if not leads:
        logger.info("No leads to deduplicate.")
        return []

    conn = _get_connection()
    cursor = conn.cursor()

    unique_leads = []
    seen_in_batch: set = set()
    dropped = 0

    for lead in leads:
        h = _make_hash(lead)

        # In-batch dedup
        if h in seen_in_batch:
            dropped += 1
            logger.debug("Duplicate within batch: %s", lead.get("company_name"))
            continue

        # DB dedup
        cursor.execute("SELECT 1 FROM seen_leads WHERE hash = ?", (h,))
        if cursor.fetchone():
            dropped += 1
            logger.debug("Already in DB: %s", lead.get("company_name"))
            continue

        seen_in_batch.add(h)
        unique_leads.append((h, lead))

    # Batch insert new hashes
    now = datetime.now(timezone.utc).isoformat()
    rows_to_insert = [
        (h, lead.get("company_name", ""), lead.get("announcement_date", ""), now)
        for h, lead in unique_leads
    ]
    if rows_to_insert:
        cursor.executemany(
            "INSERT OR IGNORE INTO seen_leads (hash, company_name, announcement_date, created_at) VALUES (?, ?, ?, ?)",
            rows_to_insert,
        )
        conn.commit()

    conn.close()

    result = [lead for _, lead in unique_leads]
    logger.info(
        "Deduplication: %d in -> %d unique, %d dropped.",
        len(leads), len(result), dropped
    )
    return result


def clear_old_records(days: int = 90) -> int:
    """
    Delete DB records older than *days* days.

    Args:
        days: retention period in days (default 90)

    Returns:
        Number of records deleted.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM seen_leads WHERE created_at < ?", (cutoff,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted:
        logger.info("Pruned %d old records (older than %d days).", deleted, days)
    return deleted
