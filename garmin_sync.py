import os
import datetime
import gspread
import json
import statistics
import traceback
from garminconnect import Garmin

# --- CONFIGURATION ---
GARMIN_EMAIL = os.environ["GARMIN_EMAIL"]
GARMIN_PASS = os.environ["GARMIN_PASS"]
GOOGLE_JSON_KEY = json.loads(os.environ["GOOGLE_JSON_KEY"]) 

# !!! PASTE YOUR SPREADSHEET ID HERE !!!
SHEET_ID = "PASTE_YOUR_ID_HERE" 
TAB_NAME = "Garmin_Stats" 

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def mps_to_pace(mps):
    if not mps or mps <= 0: return "0:00"
    minutes_per_km = 16.6667 / mps
    minutes = int(minutes_per_km)
    seconds = int((minutes_per_km - minutes) * 60)
    return f"{minutes}:{seconds:02d}"

def main():
    print("--- Starting Garmin Enduro 3 Sync (Final Fix) ---")
    
    # 1. Login
    try:
        garmin = Garmin(GARMIN_EMAIL, GARMIN_PASS)
        garmin.login()
        print("Garmin Login: Success")
    except Exception:
        print("Login Failed. Traceback:")
        traceback.print_exc()
        return

    # 2. Connect to Sheets
    try:
        gc = gspread.service_account_from_dict(GOOGLE_JSON_KEY, scopes=SCOPES)
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(TAB_NAME)
        print("Sheet Connect: Success")
    except Exception:
        print("Sheet Connect Failed.")
        traceback.print_exc()
        return

    # 3. DATE LOGIC
    # We fetch YESTERDAY's full data
    target_date = datetime.date.today() - datetime.timedelta(days=1)
    iso_date = target_date.isoformat()
    print(f"Fetching Data for: {iso_date}")

    try:
        # --- FETCH RAW DATA ---
        stats = garmin.get_stats(iso_date)
        user_summary = garmin.get_user_summary(iso_date)
        body_batt = garmin.get_body_battery(iso_date)
        sleep = garmin.get_sleep_data(iso_date)
        
        # Training Status (Grab the whole blob to parse manually)
        try:
            # We use the generic call to get the huge JSON structure you showed me
            training_status = garmin.get_training_status(iso_date) or {}
        except:
            training_status = {}

        activities = garmin.get_activities_by_date(iso_date, iso_date, "")

        # --- PARSING: THE FIXES ---
        
        # 1. VO2 Max (New Logic: Dig into 'mostRecentVO2Max')
        vo2_max = 0
        try:
            vo2_data = training_status.get('mostRecentVO2Max', {}).get('generic', {})
            vo2_max = vo2_data.get('vo2MaxValue', 0)
        except:
            vo2_max = 0
            
        # Fallback if 0
        if not vo2_max:
             vo2_max = user_summary.get('vo2Max', 0)

        # 2. Acute Load (New Logic: Find the 'acuteTrainingLoadDTO' inside dynamic device keys)
        acute_load = 0
        try:
            # Go inside 'mostRecentTrainingStatus' -> 'latestTrainingStatusData'
            # Then loop through keys (like '3607545781') to find the load
            ts_data = training_status.get('mostRecentTrainingStatus', {}).get('latestTrainingStatusData', {})
            for device_id, device_data in ts_data.items():
                if 'acuteTrainingLoadDTO' in device_data:
                    acute_load = device_data['acuteTrainingLoadDTO'].get('dailyTrainingLoadAcute', 0)
                    break # Stop once we find it
        except:
            acute_load = 0
        
        # 3. Endurance Score (Placeholder - not in your logs, defaulting to 0)
        endurance_score = 0

        # 4. Basic Health
        resting_hr = stats.get('restingHeartRate', 0)
        stress_avg = stats.get('averageStressLevel', 0)
        steps = user_summary.get('totalSteps', 0)
        total_cals = user_summary.get('totalKilocalories', 0)

        # 5. Sleep
        sleep_dto = sleep.get('dailySleepDTO', {})
        sleep_hours = round(sleep_dto.get('sleepTimeSeconds', 0) / 3600, 2)
        sleep_score = sleep_dto.get('sleepScores', {}).get('overall', {}).get('value', 0)

        # 6. Body Battery (List Fix)
        if isinstance(body_batt, list):
            body_batt = body_batt[0] if body_batt else {}
        bb_list = body_batt.get('bodyBatteryValuesArray', [])
        if bb_list:
            vals = [x[1] for x in bb_list if x[1] is not None]
            bb_high = max(vals) if vals else 0
            bb_low = min(vals) if vals else 0
        else:
            bb_high, bb_low = 0, 0

        # --- RUNNING METRICS LOOP ---
        run_dist, run_time_sec, run_count = 0, 0, 0
        run_hr_list, run_speed_list, run_cadence_list = [], [], []

        for act in activities:
            type_key = act.get('activityType', {}).get('typeKey', 'other')
            if 'running' in type_key:
                run_count += 1
                run_dist += act.get('distance', 0)
                run_time_sec += act.get('duration', 0)
                
                # HEART RATE FIX: Check 'averageHR' if 'averageHeartRate' is missing
                hr = act.get('averageHeartRate')
                if not hr:
                    hr = act.get('averageHR') # <--- The Fix
                
                speed = act.get('averageSpeed')
                cad = act.get('averageRunningCad
