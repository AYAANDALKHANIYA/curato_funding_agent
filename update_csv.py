import pandas as pd
import os

CSV_PATH = "data/leads_output.csv"
EXPECTED_COLUMNS = [
    "COMPANY NAME", "Website", "LinkedIn", "Source Url", "Collected at"
]

if os.path.exists(CSV_PATH):
    try:
        df = pd.read_csv(CSV_PATH)
        print(f"Original shape: {df.shape}")
        
        # Ensure all columns exist
        for col in EXPECTED_COLUMNS:
            if col not in df.columns:
                df[col] = ""
                
        # Reorder columns to match EXPECTED_COLUMNS exactly
        # If we only want the 5 columns, filter to just those:
        df = df[EXPECTED_COLUMNS]
        
        # Save back
        df.to_csv(CSV_PATH, index=False)
        print(f"Successfully updated CSV. New shape: {df.shape}")
        
    except Exception as e:
        print(f"Error updating CSV: {e}")
else:
    print(f"CSV not found at {CSV_PATH}")
