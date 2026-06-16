"""
src/pipeline.py
---------------
Orchestrates the full Funding & Grant Intelligence pipeline:
  1. Fetch articles (RSS + scrape)
  2. Extract leads via Groq AI
  2.5. Enrich leads with website/LinkedIn (Serper.dev)
  3. Deduplicate
  4. Score and rank
  5. Write to Google Sheets + CSV
  6. Prune old dedup records
"""

import logging
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Logging setup — called once at module level so it's ready for imports below
# ---------------------------------------------------------------------------

def _setup_logging() -> None:
    """Configure root logger to write to both stdout and a timestamped log file."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"run_{timestamp}.log")

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("feedparser").setLevel(logging.WARNING)
    return log_file


# ---------------------------------------------------------------------------
# Pipeline imports (after logging is set up)
# ---------------------------------------------------------------------------
from src.scraper import fetch_all_articles
from src.extractor import extract_all_leads
from src.enrichment import enrich_leads
from src.deduplicator import remove_duplicates, clear_old_records
from src.scorer import score_all_leads
from src.sheets import write_leads_to_sheet, write_leads_to_csv_fallback

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Main pipeline function
# ---------------------------------------------------------------------------

def run_pipeline() -> dict:
    """
    Execute the complete funding intelligence pipeline.

    Returns:
        Summary dict with counts and timing.
    """
    log_file = _setup_logging()
    start_time = time.time()
    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    logger.info("=" * 60)
    logger.info("Curato Funding Intelligence Agent — pipeline start")
    logger.info("Run timestamp: %s", run_ts)
    logger.info("=" * 60)

    # ------------------------------------------------------------------ Step 1
    logger.info("STEP 1: Fetching articles from RSS feeds and scrape sources...")
    articles = fetch_all_articles()
    n_articles = len(articles)
    logger.info("Articles fetched: %d", n_articles)

    if n_articles == 0:
        logger.warning("No articles fetched. Pipeline ending early.")
        return _summary(run_ts, 0, 0, 0, 0, start_time, log_file)

    # ------------------------------------------------------------------ Step 2
    logger.info("STEP 2: Extracting leads via Groq AI...")
    leads = extract_all_leads(articles)
    n_extracted = len(leads)
    logger.info("Leads extracted: %d", n_extracted)

    if n_extracted == 0:
        logger.warning("No leads extracted. Pipeline ending early.")
        return _summary(run_ts, n_articles, 0, 0, 0, start_time, log_file)

    # Optional enrichment with Serper (or local fallback inside enrichment.py)
    try:
        logger.info("STEP 2.5: Enriching leads (Serper.dev/local fallback)...")
        leads = enrich_leads(leads)
        logger.info("Enrichment complete.")
    except Exception as exc:
        logger.warning("Apify enrichment failed: %s", exc)

    # ------------------------------------------------------------------ Step 3
    logger.info("STEP 3: Deduplicating leads...")
    unique_leads = remove_duplicates(leads)
    n_unique = len(unique_leads)
    logger.info("Unique leads after dedup: %d", n_unique)

    # ------------------------------------------------------------------ Step 4
    logger.info("STEP 4: Scoring and ranking leads...")
    scored_leads = score_all_leads(unique_leads)
    logger.info("Leads scored: %d", len(scored_leads))

    # ------------------------------------------------------------------ Step 5
    logger.info("STEP 5: Writing leads to output...")
    n_written = 0
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "").strip()
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

    # Always write to CSV for the local dashboard
    n_written_csv = write_leads_to_csv_fallback(scored_leads)
    logger.info("Wrote %d leads to local CSV.", n_written_csv)

    if sheet_id and sa_json:
        try:
            n_written = write_leads_to_sheet(scored_leads)
            logger.info("Wrote %d leads to Google Sheets.", n_written)
        except Exception as exc:
            logger.error("Google Sheets write failed: %s.", exc)
            n_written = n_written_csv
    else:
        logger.info("Google Sheets not configured — skipping Sheets upload.")
        n_written = n_written_csv

    # ------------------------------------------------------------------ Step 6
    logger.info("STEP 6: Pruning old dedup records (90-day retention)...")
    clear_old_records(days=90)

    # ------------------------------------------------------------------ Summary
    duration = time.time() - start_time
    summary = _summary(run_ts, n_articles, n_extracted, n_unique, n_written, start_time, log_file)

    _print_summary(summary, scored_leads)
    return summary


def _summary(run_ts, n_articles, n_extracted, n_unique, n_written, start_time, log_file) -> dict:
    duration = round(time.time() - start_time, 2)
    return {
        "run_timestamp": run_ts,
        "articles_fetched": n_articles,
        "leads_extracted": n_extracted,
        "leads_after_dedup": n_unique,
        "leads_written": n_written,
        "duration_seconds": duration,
        "log_file": log_file,
    }


def _print_summary(summary: dict, scored_leads: list) -> None:
    """Print a human-readable pipeline summary and top 5 leads."""
    sep = "=" * 60
    print(f"\n{sep}")
    print("  PIPELINE SUMMARY")
    print(sep)
    print(f"  Run time        : {summary['run_timestamp']}")
    print(f"  Articles fetched: {summary['articles_fetched']}")
    print(f"  Leads extracted : {summary['leads_extracted']}")
    print(f"  After dedup     : {summary['leads_after_dedup']}")
    print(f"  Written to output: {summary['leads_written']}")
    print(f"  Duration        : {summary['duration_seconds']}s")
    print(f"  Log file        : {summary['log_file']}")
    print(sep)

    if scored_leads:
        print("\n  TOP 5 LEADS:")
        print("-" * 60)
        for i, lead in enumerate(scored_leads[:5], start=1):
            name = lead.get("company_name", "N/A")
            score = lead.get("lead_score", "?")
            atype = lead.get("announcement_type", "N/A")
            amount = lead.get("funding_amount", "N/A")
            why = lead.get("why_this_lead", "")
            print(f"  #{i} [{score}/10] {name}")
            print(f"      Type: {atype} | Amount: {amount}")
            if why:
                print(f"      Why: {why[:120]}")
            print()
    print(sep + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run_pipeline()
