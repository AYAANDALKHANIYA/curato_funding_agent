"""
src/scorer.py
-------------
Deterministic lead scoring based on announcement type and funding amount.
"""

import logging
import re

from config.sources import SCORE_MAP

logger = logging.getLogger(__name__)

# Announcement types classified as grants (scored dynamically by amount)
_GRANT_TYPES = {"grant", "accelerator grant", "innovation grant"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _score_grant(amount_usd) -> int:
    """
    Score a grant lead based on approximate USD funding amount.

    Rules:
        None            → 5
        < 50,000        → 3
        50,000–249,999  → 5
        250,000–999,999 → 7
        >= 1,000,000    → 8
    """
    if amount_usd is None:
        return 5
    try:
        amount = float(amount_usd)
    except (TypeError, ValueError):
        return 5

    if amount < 50_000:
        return 3
    elif amount < 250_000:
        return 5
    elif amount < 1_000_000:
        return 7
    else:
        return 8


def _parse_amount_usd(lead: dict):
    """
    Derive an approximate USD value from the lead.

    Priority:
      1. lead["funding_amount_usd"]  (already numeric)
      2. Parse lead["funding_amount"] string:
           - $XB / $XM / $XK  (USD billions/millions/thousands)
           - X Cr (Indian Rupees crore → USD at ~120,000 per Cr)

    Returns float or None.
    """
    # 1. Direct USD field
    raw_usd = lead.get("funding_amount_usd")
    if raw_usd is not None:
        try:
            return float(raw_usd)
        except (TypeError, ValueError):
            pass

    # 2. Parse string
    amount_str = lead.get("funding_amount", "") or ""
    if not amount_str or amount_str.strip().lower() == "undisclosed":
        return None

    amount_str = amount_str.strip()

    # USD with B/M/K suffixes  e.g. "$3M", "$1.5B", "$500K", "3M", "USD 5M"
    usd_match = re.search(
        r"\$?\s*(\d+(?:\.\d+)?)\s*([BMKbmk])\b",
        amount_str.replace(",", ""),
    )
    if usd_match:
        value = float(usd_match.group(1))
        suffix = usd_match.group(2).upper()
        multiplier = {"B": 1_000_000_000, "M": 1_000_000, "K": 1_000}[suffix]
        return value * multiplier

    # Plain USD number  e.g. "$300000" or "300,000"
    plain_usd = re.search(r"\$\s*(\d[\d,]*(?:\.\d+)?)", amount_str)
    if plain_usd:
        return float(plain_usd.group(1).replace(",", ""))

    # INR crore  e.g. "₹50 Cr", "50 Crore", "Rs. 20 Cr"
    inr_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:cr(?:ore)?)", amount_str, re.IGNORECASE)
    if inr_match:
        crore_value = float(inr_match.group(1))
        return crore_value * 120_000  # 1 Cr INR ≈ $120,000 USD

    logger.debug("Could not parse funding amount: %s", amount_str)
    return None


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def calculate_score(lead: dict) -> int:
    """
    Compute a deterministic lead score (1–10) for a single lead.

    Logic:
      - Look up announcement_type in SCORE_MAP
      - If type is a grant type → _score_grant(amount_usd)
      - Otherwise → SCORE_MAP value (default 5)
      - +1 bonus if company_stage is 'growth' or 'scale'
      - Capped at 10
    """
    announcement_type = (lead.get("announcement_type") or "").lower().strip()
    company_stage = (lead.get("company_stage") or "").lower().strip()

    # Determine base score
    if announcement_type in _GRANT_TYPES:
        amount_usd = _parse_amount_usd(lead)
        base = _score_grant(amount_usd)
    else:
        # Look up in SCORE_MAP; None value means it should use grant scoring
        mapped = SCORE_MAP.get(announcement_type)
        if mapped is None and announcement_type:
            # Type exists but has None value → grant scoring
            amount_usd = _parse_amount_usd(lead)
            base = _score_grant(amount_usd)
        else:
            base = mapped if mapped is not None else 5

    # Growth/Scale bonus
    if company_stage in ("growth", "scale"):
        base += 1

    return min(base, 10)


def score_all_leads(leads: list) -> list:
    """
    Add lead_score to every lead dict and return them sorted descending by score.

    Args:
        leads: list of lead dicts

    Returns:
        Same list with 'lead_score' key added, sorted high → low.
    """
    if not leads:
        logger.info("No leads to score.")
        return []

    for lead in leads:
        lead["lead_score"] = calculate_score(lead)

    sorted_leads = sorted(leads, key=lambda x: x.get("lead_score", 0), reverse=True)
    logger.info("Scored %d leads. Top score: %d", len(sorted_leads), sorted_leads[0]["lead_score"])
    return sorted_leads
