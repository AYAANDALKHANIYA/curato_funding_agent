# Curato — Funding & Grant Intelligence Agent

An automated Python agent that monitors startup funding news daily, extracts structured lead data using the Gemini AI API, deduplicates records, scores leads, and writes results to Google Sheets every morning at 9 AM.

**Built for Curato** — a branding and marketing agency targeting companies that have just received funding and now have budget to invest in brand identity, websites, content, and growth marketing.

---

## Features

- 📡 **Multi-source scraping** — TechCrunch, YourStory, Inc42, Entrackr, VCCircle, StartupNews.fyi, Startup India Blog
- 🤖 **AI extraction** — Gemini 1.5 Flash extracts company name, funding type, amount, location, industry, and a custom "why this lead" pitch
- 🎯 **Deterministic scoring** — 1–10 score based on funding stage and amount
- 🔁 **Deduplication** — SQLite-backed SHA-256 fingerprinting prevents repeat entries
- 📊 **Google Sheets output** — auto-creates monthly tabs and writes headers
- 📁 **CSV fallback** — works immediately without any Google setup
- ⏰ **Daily scheduler** — runs at 9 AM by default (configurable)

---

## Project Structure

```
funding-agent/
├── config/
│   ├── __init__.py
│   └── sources.py          # RSS sources, scrape targets, keywords, score map
├── src/
│   ├── __init__.py
│   ├── scraper.py          # RSS + HTML scraping
│   ├── extractor.py        # Gemini AI lead extraction
│   ├── scorer.py           # Deterministic scoring logic
│   ├── deduplicator.py     # SQLite-based deduplication
│   ├── sheets.py           # Google Sheets + CSV output
│   └── pipeline.py         # Full pipeline orchestration
├── data/                   # Auto-created: SQLite DB + CSV output
├── logs/                   # Auto-created: timestamped run logs
├── scheduler.py            # Daily scheduler entry point
├── requirements.txt
├── .env.example
├── README.md
└── SETUP_GOOGLE_SHEETS.md
```

---

## Quick Start

### 1. Install Dependencies

```bash
cd funding-agent
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and add your **Gemini API key** (required). Google Sheets is optional — the system will write to `data/leads_output.csv` if not configured.

```env
GEMINI_API_KEY=your_gemini_api_key_here
GOOGLE_SHEET_ID=your_google_sheet_id_here        # optional
GOOGLE_SERVICE_ACCOUNT_JSON=service_account.json  # optional
RUN_TIME=09:00
```

### 3. Run

```bash
# Run once immediately + start daily scheduler
python scheduler.py

# Or run the pipeline once without the scheduler
python -m src.pipeline
```

---

## Output

### Google Sheets
Leads are written to a new tab each month (e.g., `June 2025`) with these columns:

| Column | Description |
|--------|-------------|
| Company Name | Startup that received funding |
| Website | Company website URL |
| LinkedIn | LinkedIn page URL |
| Location | City, Country |
| Industry | Sector/vertical |
| Company Stage | Idea / MVP / Early Revenue / Growth / Scale / Enterprise |
| Announcement Type | Seed / Series A / Grant / etc. |
| Funding/Grant Amount | Raw amount string |
| Announcement Date | Date of the funding announcement |
| Source URL | Link to the source article |
| Lead Score | 1–10 priority score |
| Why This Lead? | One-sentence AI pitch for Curato |
| Source Name | Which news source |
| Collected At | Timestamp when collected |

### CSV Fallback
Written to `data/leads_output.csv` with the same columns.

---

## Lead Scoring

| Stage | Base Score |
|-------|-----------|
| Series B | 10 |
| Series A | 9 |
| Series C | 9 |
| Growth Round | 8 |
| Scale-Up Funding | 8 |
| Seed | 7 |
| Strategic Investment | 7 |
| Venture Debt | 6 |
| Pre-Seed | 5 |
| Angel Investment | 4 |
| Grant (dynamic) | 3–8 based on amount |

**+1 bonus** if company stage is Growth or Scale. **Capped at 10**.

---

## Verification

Run the built-in verification script to confirm scoring and deduplication work correctly:

```bash
cd funding-agent
python verify.py
```

Expected output:
```
Scores:
  TestCo: 10/10
  GrantCo: 7/10
  SeedCo: 7/10
Dedup pass 1: 4 → 3
Dedup pass 2: 4 → 0 (should be 0 — all seen)
All OK
```

---

## Google Sheets Setup

See [SETUP_GOOGLE_SHEETS.md](SETUP_GOOGLE_SHEETS.md) for the full step-by-step guide.

---

## Logs

Each run creates a timestamped log file in `logs/`:
```
logs/run_20250610_090001.log
```

---

## Notes

- Some sources (e.g., Entrackr, Inc42 behind login) may return 403 — the scraper handles these gracefully and logs the error without crashing.
- The Gemini API is called once per article. Free-tier rate limits may apply. The extractor includes a 0.5-second delay between calls.
- Deduplication is persistent across runs via SQLite. Records older than 90 days are automatically pruned.
