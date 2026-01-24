import os
import datetime
import gspread
import json
import statistics
from garminconnect import Garmin

# --- CONFIGURATION ---
GARMIN_EMAIL = os.environ["GARMIN_EMAIL"]
GARMIN_PASS = os.environ["GARMIN_PASS"]
GOOGLE_JSON_KEY = json.loads(os.environ["GOOGLE_JSON_KEY"]) 
SHEET_NAME = "Life Metrics 2026"
TAB_NAME = "Garmin_Stats" 

def mps_to_pace(mps):
    """Converts meters/second to min/km string (e.g., '5:30')"""
    if not mps or mps <= 0: return "0:00"
    minutes_per_km = 16.6667 / mps
    minutes = int(minutes_per_km)
    seconds = int((minutes_per_km - minutes) * 60)
    return f"{minutes}:{seconds:02d}"

def main():
    print("--- Starting Garmin Enduro 3 Sync ---")
    
    # 1. Login
    try:
        garmin = Garmin(GARMIN_EMAIL, GARMIN_PASS)
        garmin.login()
        print("Login: Success")
    except Exception as e:
        print(f"Login Failed: {e}")
        return

    # 2. Connect to Sheets
    try:
        gc = gspread.service_account_from_dict(GOOGLE_JSON_KEY)
        sh = gc.open(SHEET_NAME)
        worksheet = sh.worksheet(TAB_NAME)
        print("Sheet Connect: Success")
    except Exception as e:
        print(f"Sheet Connect Failed: {e}")
        return

    # 3. Define Date (Yesterday)
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    iso_date = yesterday.isoformat()
    print(f"Processing data for: {iso_date}")

    try:
        # --- A. FETCH DAILY HEALTH STATS ---
        stats = garmin.get_stats(iso_date)
        body_batt = garmin.get_body_battery(iso_date)
        sleep = garmin.get_sleep_data(iso_date)
        user_summary = garmin.get_user_summary(iso_date)
        
        # --- B. FETCH TRAINING STATUS (Acute Load, etc) ---
        # Note: These endpoints change often, we use safe gets
        training_status = garmin.get_training_status(iso_date) or {}
        fitness_age_data = garmin.get_fitness_age(iso_date) or {}

        # --- C. FETCH ACTIVITIES (The Running Loop) ---
        activities = garmin.get_activities_by_date(iso_date, iso_date, "")
        
        # --- PARSING PART 1: DAILY METRICS ---
        resting_hr = stats.get('restingHeartRate', 0)
        stress_avg = stats.get('averageStressLevel', 0)
        steps = user_summary.get('totalSteps', 0)
        total_cals = user_summary.get('totalKilocalories', 0) # Active + Resting
        vo2_max = user_summary.get('vo2Max', 0)

        # Sleep
        sleep_dto = sleep.get('dailySleepDTO', {})
        sleep_hours = round(sleep_dto.get('sleepTimeSeconds', 0) / 3600, 2)
        sleep_score = sleep_dto.get('sleepScores', {}).get('overall', {}).get('value', 0)

        # Body Battery
        bb_list = body_batt.get('bodyBatteryValuesArray', [])
        if bb_list:
            vals = [x[1] for x in bb_list if x[1] is not None]
            bb_high = max(vals) if vals else 0
            bb_low = min(vals) if vals else 0
        else:
            bb_high, bb_low = 0, 0

        # Advanced Training Metrics
        # Fitness Age might be directly in value or nested
        fit_age = fitness_age_data.get('fitnessAge', 0)
        
        # Acute Load (7-Day Load)
        acute_load = 0
        endurance_score = 0 # This is very new, might not be in API yet, placeholder
        
        # Try to find Acute Load in the messy Training Status JSON
        if training_status:
            # Often located in 'mostRecentActivityTrainingLoad' or similar
            acute_load = training_status.get('acuteTrainingLoadValue', 0)
            endurance_score = training_status.get('enduranceScore', 0) # Attempt to fetch

        # --- PARSING PART 2: RUNNING SPECIFICS ---
        run_dist = 0
        run_time_sec = 0
        run_hr_list = []
        run_speed_list = [] # m/s
        run_cadence_list = []
        run_count = 0
        total_activity_time_sec = 0

        for act in activities:
            total_activity_time_sec += act.get('duration', 0)
            
            # Check if it's a run (Type 1 is usually running, but we check key)
            act_type = act.get('activityType', {}).get('typeKey', '')
            if 'running' in act_type:
                run_count += 1
                run_dist += act.get('distance', 0) # Meters
                run_time_sec += act.get('duration', 0)
                
                if act.get('averageHeartRate'):
                    run_hr_list.append(act['averageHeartRate'])
                if act.get('averageSpeed'):
                    run_speed_list.append(act['averageSpeed'])
                if act.get('averageRunningCadenceInStepsPerMinute'):
                    run_cadence_list.append(act['averageRunningCadenceInStepsPerMinute'])

        # Calculate Running Averages
        avg_run_hr = int(statistics.mean(run_hr_list)) if run_hr_list else 0
        avg_run_cadence = int(statistics.mean(run_cadence_list)) if run_cadence_list else 0
        
        # Speed math (Average the speeds, then convert to pace)
        avg_mps = statistics.mean(run_speed_list) if run_speed_list else 0
        avg_pace_str = mps_to_pace(avg_mps)
        
        # Unit Conversions
        run_dist_km = round(run_dist / 1000, 2)
        total_activity_time_min = round(total_activity_time_sec / 60, 0)

        print(f"Runs Found: {run_count} | Dist: {run_dist_km}km | Pace: {avg_pace_str}")

        # --- SEND TO SHEETS ---
        # 1. Date | 2. RHR | 3. Stress | 4. Sleep Score | 5. Sleep Hrs 
        # 6. BB High | 7. BB Low | 8. VO2 Max | 9. Fit Age | 10. Acute Load 
        # 11. Endur Score | 12. Steps | 13. Cals | 14. Activity Time 
        # 15. Run Dist | 16. Run HR | 17. Run Pace | 18. Run Cadence | 19. Count
        
        row_data = [
            iso_date, resting_hr, stress_avg, sleep_score, sleep_hours,
            bb_high, bb_low, vo2_max, fit_age, acute_load,
            endurance_score, steps, total_cals, total_activity_time_min,
            run_dist_km, avg_run_hr, avg_pace_str, avg_run_cadence, run_count
        ]

        worksheet.append_row(row_data)
        print("Success: Pro Metrics uploaded.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
