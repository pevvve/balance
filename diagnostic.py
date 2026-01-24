import os
import datetime
import json
from garminconnect import Garmin

# --- CONFIGURATION ---
GARMIN_EMAIL = os.environ["GARMIN_EMAIL"]
GARMIN_PASS = os.environ["GARMIN_PASS"]

def main():
    print("--- DIAGNOSTIC RUN: SEARCHING FOR MISSING VARIABLES ---")
    
    try:
        garmin = Garmin(GARMIN_EMAIL, GARMIN_PASS)
        garmin.login()
        print("Login: Success")
    except Exception as e:
        print(f"Login Failed: {e}")
        return

    # Look at Yesterday
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    iso_date = yesterday.isoformat()
    print(f"Inspecting Data for: {iso_date}")

    # 1. HUNT FOR FITNESS AGE
    print("\n[1] SEARCHING FOR FITNESS AGE...")
    try:
        # We try the direct call first
        fit_age = garmin.get_fitness_age(iso_date)
        print(f" > RESULT: {fit_age}")
    except Exception as e:
        print(f" > Direct call failed: {e}")
        print(" > Checking User Summary instead...")
        try:
            summary = garmin.get_user_summary(iso_date)
            print(f" > In Summary? {summary.get('fitnessAge')}")
        except:
            print(" > Not in summary.")

    # 2. HUNT FOR RUNNING HEART RATE
    print("\n[2] SEARCHING FOR RUNNING HEART RATE...")
    activities = garmin.get_activities_by_date(iso_date, iso_date, "")
    
    run_found = False
    for act in activities:
        type_key = act.get('activityType', {}).get('typeKey', 'other')
        if 'running' in type_key:
            run_found = True
            print(f" > Found Run ID: {act.get('activityId')}")
            # Check for HR under different common names
            print(f" > 'averageHeartRate': {act.get('averageHeartRate')}")
            print(f" > 'avgHR': {act.get('avgHR')}")
            print(f" > 'averageHR': {act.get('averageHR')}")
            # Print all keys to see if they hid it somewhere else
            print(f" > ALL KEYS: {list(act.keys())}")
            break
            
    if not run_found:
        print(" > No running activity found.")

    # 3. HUNT FOR VO2 MAX & LOAD
    print("\n[3] SEARCHING FOR VO2 MAX & LOAD...")
    try:
        # Fetch generic Training Status
        status = garmin.get_training_status(iso_date)
        print(f" > RAW TRAINING STATUS: {status}")
    except Exception as e:
        print(f" > Training Status failed: {e}")

if __name__ == "__main__":
    main()
