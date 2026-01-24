import os
import datetime
import gspread
import json
from garminconnect import Garmin

# --- CONFIGURATION ---
GARMIN_EMAIL = os.environ["GARMIN_EMAIL"]
GARMIN_PASS = os.environ["GARMIN_PASS"]
# We load the JSON string directly from the secret
GOOGLE_JSON_KEY = json.loads(os.environ["GOOGLE_JSON_KEY"]) 
SHEET_NAME = "Life Metrics 2026"
TAB_NAME = "Garmin_Stats" 

def main():
    print("--- Starting Garmin Sync ---")
    
    # 1. Connect to Garmin
    try:
        print("Logging into Garmin...")
        garmin = Garmin(GARMIN_EMAIL, GARMIN_PASS)
        garmin.login()
    except Exception as e:
        print(f"Failed to login to Garmin: {e}")
        return

    # 2. Connect to Google Sheets
    try:
        print("Connecting to Google Sheets...")
        # gspread can read the dictionary directly, no need to save to file
        gc = gspread.service_account_from_dict(GOOGLE_JSON_KEY)
        sh = gc.open(SHEET_NAME)
        worksheet = sh.worksheet(TAB_NAME)
    except Exception as e:
        print(f"Failed to connect to Google Sheets: {e}")
        print("Double check that you shared the sheet with the client_email inside your JSON file!")
        return

    # 3. Fetch Data (Yesterday's data to ensure it is complete)
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    iso_date = yesterday.isoformat()
    
    print(f"Fetching stats for {iso_date}...")
    
    try:
        # Fetch specific endpoints
        stats = garmin.get_stats(iso_date)
        body_battery = garmin.get_body_battery(iso_date)
        sleep = garmin.get_sleep_data(iso_date)
        
        # 4. Extract Key Metrics
        # General Stats
        resting_hr = stats.get('restingHeartRate', 0)
        stress_avg = stats.get('averageStressLevel', 0)
        
        # Body Battery (High/Low)
        bb_list = body_battery.get('bodyBatteryValuesArray', [])
        bb_high = max([x[1] for x in bb_list]) if bb_list else 0
        bb_low = min([x[1] for x in bb_list]) if bb_list else 0
        
        # Sleep (Seconds to Hours)
        sleep_seconds = sleep.get('dailySleepDTO', {}).get('sleepTimeSeconds', 0)
        sleep_hours = round(sleep_seconds / 3600, 2)
        sleep_score = sleep.get('dailySleepDTO', {}).get('sleepScores', {}).get('overall', {}).get('value', 0)

        print(f"Data found -> Stress: {stress_avg}, Sleep: {sleep_hours}h, BB High: {bb_high}")

        # 5. Append to Google Sheet
        # Row format: Date | RHR | Stress | Sleep Hrs | Sleep Score | BB High | BB Low
        row_data = [
            iso_date,
            resting_hr,
            stress_avg,
            sleep_hours,
            sleep_score,
            bb_high,
            bb_low
        ]
        
        worksheet.append_row(row_data)
        print("Success! Data appended.")

    except Exception as e:
        print(f"Error parsing Garmin data: {e}")
        return

if __name__ == "__main__":
    main()
