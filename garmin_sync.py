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

# !!! PASTE YOUR COPIED ID INSIDE THE QUOTES BELOW !!!
SHEET_ID = "1wCX2fT-YYi67ZmlrZLq6xc--l1mVyuG3Bv5Z9h0NNJw" 
TAB_NAME = "Garmin" 

# Define explicit scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def mps_to_pace(mps):
    """Converts meters/second to min/km string"""
    if not mps or mps <= 0: return "0:00"
    minutes_per_km = 16.6667 / mps
    minutes = int(minutes_per_km)
    seconds = int((minutes_per_km - minutes) * 60)
    return f"{minutes}:{seconds:02d}"

def main():
    print("--- Starting Garmin Enduro 3 Sync (Fixed List Bug) ---")
    
    # 1. Login
    try:
        garmin = Garmin(GARMIN_EMAIL, GARMIN_PASS)
        garmin.login()
        print("Garmin Login: Success")
    except Exception:
        print("Garmin Login Failed! Traceback:")
        traceback.print_exc()
        return

    # 2. Connect to Sheets
    try:
        print("Authenticating with Google...")
        gc = gspread.service_account_from_dict(GOOGLE_JSON_KEY, scopes=SCOPES)
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(TAB_NAME)
        print("Sheet Connect: Success")
    except Exception:
        print("\n!!! SHEET CONNECT FAILED !!!")
        print("Traceback:")
        traceback.print_exc()
        return

    # 3. Define Date (Yesterday)
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    iso_date = yesterday.isoformat()
    print(f"Processing data for: {iso_date}")

    try:
        # --- FETCH DATA ---
        stats = garmin.get_stats(iso_date)
        body_batt = garmin.get_body_battery(iso_date)
        sleep = garmin.get_sleep_data(iso_date)
        user_summary = garmin.get_user_summary(iso_date)
        
        try:
            training_status = garmin.get_training_status(iso_date) or {}
        except:
            training_status = {}
            
        activities = garmin.get_activities_by_date(iso_date, iso_date, "")
        
        # --- PARSING ---
        resting_hr = stats.get('restingHeartRate', 0)
        stress_avg = stats.get('averageStressLevel', 0)
        steps = user_summary.get('totalSteps', 0)
        total_cals = user_summary.get('totalKilocalories', 0)
        vo2_max = user_summary.get('vo2Max', 0)

        # Sleep
        sleep_dto = sleep.get('dailySleepDTO', {})
        sleep_hours = round(sleep_dto.get('sleepTimeSeconds', 0) / 3600, 2)
        sleep_score = sleep_dto.get('sleepScores', {}).get('overall', {}).get('value', 0)

        # --- BODY BATTERY FIX ---
        # If API returns a list, grab the first item. If dict, use it directly.
        if isinstance(body_batt, list):
            body_batt = body_batt[0] if body_batt else {}
            
        bb_list = body_batt.get('bodyBatteryValuesArray', [])
        if bb_list:
            vals = [x[1] for x in bb_list if x[1] is not None]
            bb_high = max(vals) if vals else 0
            bb_low = min(vals) if vals else 0
        else:
            bb_high, bb_low = 0, 0

        # Training Metrics
        acute_load = training_status.get('acuteTrainingLoadValue', 0)
        endurance_score = training_status.get('enduranceScore', 0)

        # --- RUNNING METRICS ---
        run_dist, run_time_sec, run_count = 0, 0, 0
        run_hr_list, run_speed_list, run_cadence_list = [], [], []

        for act in activities:
            act_type = act.get('activityType', {}).get('typeKey', '')
            if 'running' in act_type:
                run_count += 1
                run_dist += act.get('distance', 0)
                run_time_sec += act.get('duration', 0)
                if act.get('averageHeartRate'): run_hr_list.append(act['averageHeartRate'])
                if act.get('averageSpeed'): run_speed_list.append(act['averageSpeed'])
                if act.get('averageRunningCadenceInStepsPerMinute'): run_cadence_list.append(act['averageRunningCadenceInStepsPerMinute'])

        avg_run_hr = int(statistics.mean(run_hr_list)) if run_hr_list else 0
        avg_run_cadence = int(statistics.mean(run_cadence_list)) if run_cadence_list else 0
        avg_mps = statistics.mean(run_speed_list) if run_speed_list else 0
        avg_pace_str = mps_to_pace(avg_mps)
        
        run_dist_km = round(run_dist / 1000, 2)
        total_activity_time_min = round(run_time_sec / 60, 0)

        print(f"Stats: RHR {resting_hr}, Sleep {sleep_hours}h, Runs {run_count}")

        # --- UPLOAD ---
        # Note: 'fit_age' is removed. List has 18 items.
        row_data = [
            iso_date, resting_hr, stress_avg, sleep_score, sleep_hours,
            bb_high, bb_low, vo2_max, acute_load,
            endurance_score, steps, total_cals, total_activity_time_min,
            run_dist_km, avg_run_hr, avg_pace_str, avg_run_cadence, run_count
        ]

        worksheet.append_row(row_data)
        print("Success: Metrics uploaded.")

    except Exception:
        print("Error processing/uploading data:")
        traceback.print_exc()

if __name__ == "__main__":
    main()
