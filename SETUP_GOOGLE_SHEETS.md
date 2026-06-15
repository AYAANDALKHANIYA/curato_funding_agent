# Google Sheets Integration Setup Guide

Follow these steps to connect the Curato Funding Intelligence Agent to Google Sheets.

---

## Step 1: Create a Google Cloud Project

1. Go to [https://console.cloud.google.com/](https://console.cloud.google.com/)
2. Click **"Select a project"** → **"New Project"**
3. Name it something like `curato-funding-agent`
4. Click **"Create"**

---

## Step 2: Enable the Required APIs

With your new project selected:

1. Go to **APIs & Services → Library**
2. Search for **"Google Sheets API"** → Click it → Click **"Enable"**
3. Go back to Library, search for **"Google Drive API"** → Click it → Click **"Enable"**

---

## Step 3: Create a Service Account

1. Go to **APIs & Services → Credentials**
2. Click **"+ Create Credentials"** → **"Service Account"**
3. Fill in:
   - **Service account name**: `funding-agent`
   - **Service account ID**: auto-filled
4. Click **"Create and Continue"**
5. For Role, select **"Editor"** (or at minimum "Viewer" for read, but you need Editor to write)
6. Click **"Continue"** → **"Done"**

### Download the JSON Key

1. In the Credentials page, click on your newly created service account
2. Go to the **"Keys"** tab
3. Click **"Add Key"** → **"Create new key"**
4. Select **"JSON"** → Click **"Create"**
5. A JSON file will be downloaded. **Rename it** to `service_account.json`
6. **Move it** into the `funding-agent/` directory (same level as `scheduler.py`)

> ⚠️ **Security**: Never commit `service_account.json` to Git. Add it to `.gitignore`.

---

## Step 4: Create a Google Sheet

1. Go to [https://sheets.google.com](https://sheets.google.com)
2. Create a new blank spreadsheet
3. Give it a name like **"Curato Lead Intelligence"**
4. Copy the **Sheet ID** from the URL:
   ```
   https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID_HERE/edit
   ```
   The Sheet ID is the long string between `/d/` and `/edit`.

---

## Step 5: Share the Sheet with the Service Account

1. Open your Google Sheet
2. Click **"Share"** (top right)
3. In the "Add people" field, paste the service account email address
   - Found in `service_account.json` under the `"client_email"` key
   - Looks like: `funding-agent@your-project.iam.gserviceaccount.com`
4. Set permission to **"Editor"**
5. Uncheck "Notify people" (service accounts don't have inboxes)
6. Click **"Share"**

---

## Step 6: Configure Your .env File

1. Copy the example env file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and fill in your values:
   ```env
   GEMINI_API_KEY=AIza...your_actual_key...
   GOOGLE_SHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
   GOOGLE_SERVICE_ACCOUNT_JSON=service_account.json
   RUN_TIME=09:00
   ```

---

## Step 7: Install Dependencies and Run

```bash
# Navigate to the project directory
cd funding-agent

# Install dependencies
pip install -r requirements.txt

# Run the pipeline once (no scheduler)
python -m src.pipeline

# Or run with the daily scheduler (runs immediately + every day at RUN_TIME)
python scheduler.py
```

---

## Verifying the Connection

After running, check your Google Sheet. You should see:
- A new tab named with the current month (e.g., `June 2025`)
- Headers in row 1
- Lead data starting from row 2

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `gspread.exceptions.SpreadsheetNotFound` | Check `GOOGLE_SHEET_ID` is correct and sheet is shared with the service account |
| `google.auth.exceptions.DefaultCredentialsError` | Check `GOOGLE_SERVICE_ACCOUNT_JSON` path points to the correct file |
| `403 Forbidden` on Drive API | Make sure Google Drive API is enabled in your Cloud project |
| `HttpError 403` on Sheets API | Make sure Google Sheets API is enabled + service account has Editor access |
| Falls back to CSV | Check all env vars are set; CSV at `data/leads_output.csv` is always a valid fallback |

---

## File Structure After Setup

```
funding-agent/
├── service_account.json    ← your downloaded key (never commit this!)
├── .env                    ← your configured environment variables
├── .env.example            ← template (safe to commit)
└── ...
```

---

## Adding to .gitignore

Create or update `.gitignore` in the `funding-agent/` directory:

```gitignore
.env
service_account.json
data/
logs/
__pycache__/
*.pyc
```
