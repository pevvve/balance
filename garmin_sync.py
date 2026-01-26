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
SHEET_ID = "1wCX2fT-YYi67ZmlrZLq6xc--l1mVyuG3Bv5Z9h0NNJw" 
TAB_NAME = "Garmin" 

SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

def mps_to_pace(mps):
    if not mps or mps <= 0: return "0:00"
    minutes_per_km = 16.6667 / mps
    minutes = int(minutes_per_km)
    seconds = int((minutes_per_km - minutes) * 60)
    return f"{minutes}:{seconds:02d}"

def main():
    print("--- Starting Garmin Enduro 3 Sync (Global + Run Logic) ---")
    
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

    # 3. DATE LOGIC (Yesterday)
    target_date = datetime.date.today() - datetime.timedelta(days=1)
    iso_date = target_date.isoformat()
    print(f"Fetching Data for: {iso_date}")

    try:
        # --- FETCH RAW DATA ---
        stats = garmin.get_stats(iso_date)
        user_summary = garmin.get_user_summary(iso_date)
        body_batt = garmin.get_body_battery(iso_date)
        sleep = garmin.get_sleep_data(iso_date)
        try:
            training_status = garmin.get_training_status(iso_date) or {}
        except:
            training_status = {}
        activities = garmin.get_activities_by_date(iso_date, iso_date, "")

        # --- PARSING ---
        # VO2 Max
        vo2_max = 0
        try:
            vo2_data = training_status.get('mostRecentVO2Max', {}).get('generic', {})
            vo2_max = vo2_data.get('vo2MaxValue', 0)
        except:
            vo2_max = 0
        if not vo2_max: vo2_max = user_summary.get('vo2Max', 0)

        # Acute Load
        acute_load = 0
        try:
            ts_data = training_status.get('mostRecentTrainingStatus', {}).get('latestTrainingStatusData', {})
            for device_id, device_data in ts_data.items():
                if 'acuteTrainingLoadDTO' in device_data:
                    acute_load = device_data['acuteTrainingLoadDTO'].get('dailyTrainingLoadAcute', 0)
                    break 
        except:
            acute_load = 0
        
        endurance_score = 0
        resting_hr = stats.get('restingHeartRate', 0)
        stress_avg = stats.get('averageStressLevel', 0)
        steps = user_summary.get('totalSteps', 0)
        total_cals = user_summary.get('totalKilocalories', 0)

        # Sleep
        sleep_dto = sleep.get('dailySleepDTO', {})
        sleep_hours = round(sleep_dto.get('sleepTimeSeconds', 0) / 3600, 2)
        sleep_score = sleep_dto.get('sleepScores', {}).get('overall', {}).get('value', 0)

        # Body Battery
        if isinstance(body_batt, list):
            body_batt = body_batt[0] if body_batt else {}
        bb_list = body_batt.get('bodyBatteryValuesArray', [])
        if bb_list:
            vals = [x[1] for x in bb_list if x[1] is not None]
            bb_high = max(vals) if vals else 0
            bb_low = min(vals) if vals else 0
        else:
            bb_high, bb_low = 0, 0

        # --- ACTIVITY LOGIC (UPDATED) ---
        activity_count = 0
        total_duration_seconds = 0
        
        run_dist = 0
        run_hr_list, run_speed_list, run_cadence_list = [], [], []

        for act in activities:
            # 1. GLOBAL: Count EVERYTHING (Strength, Cycling, etc.)
            activity_count += 1
            total_duration_seconds += act.get('duration', 0)

            # 2. SPECIFIC: Only run metrics if 'running'
            type_key = act.get('activityType', {}).get('typeKey', 'other')
            if 'running' in type_key:
                run_dist += act.get('distance', 0)
                
                hr = act.get('averageHeartRate')
                if not hr: hr = act.get('averageHR')
                
                speed = act.get('averageSpeed')
                cad = act.get('averageRunningCadenceInStepsPerMinute')
                
                if hr: run_hr_list.append(hr)
                if speed: run_speed_list.append(speed)
                if cad: run_cadence_list.append(cad)

        # Averages
        avg_run_hr = int(statistics.mean(run_hr_list)) if run_hr_list else 0
        avg_run_cadence = int(statistics.mean(run_cadence_list)) if run_cadence_list else 0
        avg_mps = statistics.mean(run_speed_list) if run_speed_list else 0
        avg_pace_str = mps_to_pace(avg_mps)
        
        run_dist_km = round(run_dist / 1000, 2)
        total_activity_time_min = round(total_duration_seconds / 60, 0)

        print(f"Stats Found -> Activities: {activity_count} | Mins: {total_activity_time_min} | Runs: {len(run_hr_list)}")

        # --- UPLOAD ---
        row_data = [
            iso_date, resting_hr, stress_avg, sleep_score, sleep_hours,
            bb_high, bb_low, vo2_max, acute_load,
            endurance_score, steps, total_cals, total_activity_time_min,
            run_dist_km, avg_run_hr, avg_pace_str, avg_run_cadence, activity_count
        ]

        worksheet.append_row(row_data)
        print("Success: Data uploaded.")

    except Exception:
        print("Sync Error:")
        traceback.print_exc()

if __name__ == "__main__":
    main()
