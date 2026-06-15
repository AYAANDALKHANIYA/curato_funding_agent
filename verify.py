"""
verify.py
---------
Verification script to confirm that scoring and deduplication work correctly.

Expected output:
  Scores:
    TestCo: 10/10
    GrantCo: 7/10
    SeedCo: 7/10
  Dedup pass 1: 4 → 3
  Dedup pass 2: 4 → 0 (should be 0 — all seen)
  All OK

Run from the funding-agent/ directory:
  python verify.py
"""

import os
import sys

# Ensure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Clean up any leftover test DB from a previous verify run
_test_db = os.path.join(os.path.dirname(__file__), "data", "seen_leads.db")
if os.path.exists(_test_db):
    os.remove(_test_db)

from config.sources import RSS_SOURCES, SCORE_MAP, FUNDING_KEYWORDS
from src.scorer import score_all_leads
from src.deduplicator import remove_duplicates

test_leads = [
    {
        "company_name": "TestCo",
        "announcement_type": "Series A",
        "company_stage": "Growth",
        "funding_amount": "$5M",
        "announcement_date": "2025-06-10",
        "source_url": "",
        "source_name": "test",
    },
    {
        "company_name": "GrantCo",
        "announcement_type": "Grant",
        "company_stage": "MVP",
        "funding_amount": "$300K",
        "funding_amount_usd": 300000,
        "announcement_date": "2025-06-10",
        "source_url": "",
        "source_name": "test",
    },
    {
        "company_name": "SeedCo",
        "announcement_type": "Seed",
        "company_stage": "Early Revenue",
        "funding_amount": "$1M",
        "announcement_date": "2025-06-10",
        "source_url": "",
        "source_name": "test",
    },
    {
        "company_name": "TestCo",          # Duplicate of first entry
        "announcement_type": "Series A",
        "company_stage": "Growth",
        "funding_amount": "$5M",
        "announcement_date": "2025-06-10",
        "source_url": "",
        "source_name": "test",
    },
]

# --- Deduplication first (to get 3 unique leads for scoring display) ---
# The spec expects scoring output to show 3 leads (after dedup removes the duplicate TestCo).
unique_for_scoring = remove_duplicates(test_leads)

# --- Scoring (on unique leads) ---
scored = score_all_leads(unique_for_scoring)
print("Scores:")
for lead in scored:
    print(f"  {lead['company_name']}: {lead['lead_score']}/10")

# --- Deduplication pass 2 (all 4 original leads are now in the DB) ---
unique2 = remove_duplicates(test_leads)
print(f"Dedup pass 1: {len(test_leads)} -> {len(unique_for_scoring)}")
print(f"Dedup pass 2: {len(test_leads)} -> {len(unique2)} (should be 0 -- all seen)")

# --- Assertions ---
assert scored[0]["company_name"] == "TestCo", f"Expected TestCo first, got {scored[0]['company_name']}"
assert scored[0]["lead_score"] == 10, f"TestCo score should be 10, got {scored[0]['lead_score']}"

grant_co = next(l for l in scored if l["company_name"] == "GrantCo")
assert grant_co["lead_score"] == 7, f"GrantCo score should be 7, got {grant_co['lead_score']}"

seed_co = next(l for l in scored if l["company_name"] == "SeedCo")
assert seed_co["lead_score"] == 7, f"SeedCo score should be 7, got {seed_co['lead_score']}"

assert len(unique_for_scoring) == 3, f"Expected 3 unique leads, got {len(unique_for_scoring)}"
assert len(unique2) == 0, f"Expected 0 unique leads on second pass, got {len(unique2)}"

print("All OK")
