"""
scheduler.py
------------
Runs the pipeline immediately on startup, then schedules it daily at RUN_TIME.
"""

import logging
import os
import sys
import time

import schedule
from dotenv import load_dotenv

# Load environment before anything else
load_dotenv()

# Ensure project root is on sys.path so imports work from any CWD
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.pipeline import run_pipeline

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schedule configuration
# ---------------------------------------------------------------------------
RUN_TIME = os.environ.get("RUN_TIME", "09:00").strip()


def _scheduled_job() -> None:
    """Wrapper so schedule can call run_pipeline and log any errors."""
    logger.info("Scheduled job triggered at %s.", RUN_TIME)
    try:
        run_pipeline()
    except Exception as exc:
        logger.error("Pipeline error during scheduled run: %s", exc, exc_info=True)


def main() -> None:
    logger.info("=" * 60)
    logger.info("Curato Funding Intelligence Agent — scheduler starting")
    logger.info("Daily run scheduled at: %s", RUN_TIME)
    logger.info("=" * 60)

    # Schedule daily job
    schedule.every().day.at(RUN_TIME).do(_scheduled_job)

    # Log when the next run is
    next_run = schedule.next_run()
    logger.info("Next scheduled run: %s", next_run)

    # Run immediately on startup so you can verify everything works
    logger.info("Running pipeline immediately on startup...")
    try:
        run_pipeline()
    except Exception as exc:
        logger.error("Pipeline error during startup run: %s", exc, exc_info=True)

    # Main loop
    logger.info("Entering scheduler loop (checks every 60 seconds)...")
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
