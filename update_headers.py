import os
import sys
import logging
from datetime import datetime

from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

# Load environment variables
load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_HEADERS = [
    "COMPANY NAME",
    "Website",
    "LinkedIn",
    "Source Url",
    "Collected at",
]

def main():
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    json_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")

    if not sheet_id or not json_path:
        print("Missing Google Sheets credentials in environment variables.")
        return

    # Connect to Google Sheets
    creds = Credentials.from_service_account_file(json_path, scopes=SCOPES)
    client = gspread.authorize(creds)
    
    try:
        spreadsheet = client.open_by_key(sheet_id)
    except Exception as e:
        print(f"Failed to open spreadsheet: {e}")
        return

    # We want to update the current month's tab (and possibly all tabs if they exist)
    # The pipeline uses the current month. Let's update all worksheets for safety.
    for worksheet in spreadsheet.worksheets():
        try:
            print(f"Updating headers for worksheet: {worksheet.title}")
            # Update row 1
            worksheet.update("A1:E1", [SHEET_HEADERS])
            print(f"Successfully updated headers in {worksheet.title}")
        except Exception as e:
            print(f"Failed to update worksheet {worksheet.title}: {e}")

if __name__ == "__main__":
    main()
