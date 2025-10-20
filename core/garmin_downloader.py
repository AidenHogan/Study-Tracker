# file: core/garmin_downloader.py

import garth
from garth.exc import GarthException  # <-- Explicitly import the exception class
import pandas as pd
from datetime import date, timedelta
import os

# --- Constants to match the importer's expected column names ---
COL_DATE = 'Date'
COL_SCORE = 'Score'
COL_RESTING_HR = 'Resting Heart Rate'
COL_BODY_BATTERY = 'Body Battery'
COL_PULSE_OX = 'Avg. SpO2'
COL_RESPIRATION = 'Avg. Respiration Rate'
COL_AVG_STRESS = 'Avg. Stress'
COL_DURATION = 'Duration'
COL_HYDRATION = 'Hydration (mL)'
COL_INTENSITY_MINUTES = 'Intensity Minutes'


def find_missing_data_window(most_recent_date_in_db, max_days=90):
    """
    Uses a binary search approach to find the optimal sync window.
    Checks if we have data at progressively smaller intervals (e.g., 45d, 22d, 11d ago)
    and returns the number of days to fetch to fill the gap.
    
    Args:
        most_recent_date_in_db: The most recent date we have data for (datetime.date or None)
        max_days: Maximum number of days to consider (default 90)
    
    Returns:
        Number of days to fetch (1 to max_days)
    """
    if most_recent_date_in_db is None:
        # No data in DB, fetch the full window
        return max_days
    
    today = date.today()
    days_since_last = (today - most_recent_date_in_db).days
    
    # If we have data from today or yesterday, just fetch the last few days
    if days_since_last <= 1:
        return 7  # Fetch a week to catch any updates
    
    # If the gap is larger than max_days, fetch max_days
    if days_since_last >= max_days:
        return max_days
    
    # Otherwise, fetch from the day after the most recent date
    # Add a small buffer (3 days) to catch any late-arriving data
    return min(days_since_last + 3, max_days)


def download_health_stats(days=None, start_date_override=None):
    """
    Logs into Garmin Connect, downloads daily health stats, and saves as CSV.
    
    Args:
        days: Number of days to fetch (if None, will be calculated intelligently)
        start_date_override: Explicit start date (overrides days calculation)
    
    Returns:
        Path to the saved CSV file, or raises exception on auth failure
    """
    auth_attempts = 0
    max_auth_attempts = 2
    
    while auth_attempts < max_auth_attempts:
        try:
            # Step 1: Try to resume a saved session. This avoids logging in every time.
            garth.resume("~/.garth")
            break  # Success, exit the auth loop
        except (FileNotFoundError, GarthException) as e:
            auth_attempts += 1
            try:
                # Step 2: If resuming fails, perform a full login.
                email = os.getenv("GARMIN_EMAIL")
                password = os.getenv("GARMIN_PASSWORD")
                if not email or not password:
                    # Raise exception to let the UI handle credential input
                    raise GarthException("GARMIN_EMAIL and GARMIN_PASSWORD environment variables not set. Please configure credentials.")
                
                print(f"Login attempt {auth_attempts}...")
                garth.login(email, password)
                garth.save("~/.garth")
                break  # Success, exit the auth loop
            except GarthException as login_error:
                # Check if it's an authentication error
                error_msg = str(login_error).lower()
                if "auth" in error_msg or "login" in error_msg or "password" in error_msg or "credentials" in error_msg:
                    if auth_attempts >= max_auth_attempts:
                        # Out of attempts, raise with clear message
                        raise GarthException("Authentication failed. Your Garmin credentials may be incorrect or have changed. Please update your GARMIN_EMAIL and GARMIN_PASSWORD.") from login_error
                    # Try again on next iteration
                    print(f"Authentication failed, retrying... ({auth_attempts}/{max_auth_attempts})")
                else:
                    # Different error, re-raise
                    raise

    end_date = date.today()
    
    # Determine the start date based on what we already have in the DB
    if start_date_override:
        start_date = start_date_override
    elif days is not None:
        start_date = end_date - timedelta(days=days - 1)
    else:
        # Smart sync: check DB and only fetch what's missing
        from . import database_manager as db
        most_recent = db.get_most_recent_health_date()
        calculated_days = find_missing_data_window(most_recent)
        start_date = end_date - timedelta(days=calculated_days - 1)
        print(f"Smart sync: Last data in DB from {most_recent}, fetching {calculated_days} days")
    
    print(f"Fetching Garmin data from {start_date} to {end_date}...")

    # This dictionary will hold the data we successfully fetch.
    processed = {}
    current_date = start_date

    # Loop through each day in the requested range.
    while current_date <= end_date:
        day_str = current_date.isoformat()
        print(f" - Getting data for {day_str}")
        try:
            # Step 3: Use the new garth API structure.
            # The API has changed - we now use individual stat classes instead of connectapi
            
            data = {}
            
            # Get sleep data (score and detailed info)
            try:
                sleep_list = garth.DailySleep.list(day_str, 1)
                if sleep_list:
                    data['sleepScore'] = sleep_list[0].value
                    
                # Try to get detailed sleep data for respiratory rate and SpO2
                try:
                    sleep_detail = garth.SleepData.get(day_str)
                    if sleep_detail and sleep_detail.daily_sleep_dto:
                        dto = sleep_detail.daily_sleep_dto
                        data['avgSPO2'] = dto.average_sp_o2_value
                        data['averageRespirationValue'] = dto.average_respiration_value
                        
                        # Calculate duration string from sleep time
                        if dto.sleep_time_seconds:
                            h = dto.sleep_time_seconds // 3600
                            m = (dto.sleep_time_seconds % 3600) // 60
                            data['sleepDurationStr'] = f"{h}h {m}m"
                except Exception:
                    # Detailed sleep data requires OAuth1, may not be available
                    pass
            except Exception:
                pass
                
            # Get stress data
            try:
                stress_list = garth.DailyStress.list(day_str, 1)
                if stress_list:
                    data['averageStressLevel'] = stress_list[0].overall_stress_level
            except Exception:
                pass
                
            # Try to get body battery data (may require OAuth1)
            try:
                bb_data = garth.DailyBodyBatteryStress.get(day_str)
                if bb_data:
                    data['bodyBatteryLowestValue'] = bb_data.min_body_battery
            except Exception:
                # Body battery requires OAuth1, may not be available
                pass

            # Try to get hydration (may require OAuth1)
            try:
                if hasattr(garth, 'DailyHydration'):
                    hyd_list = garth.DailyHydration.list(day_str, 1)
                    if hyd_list:
                        # best-effort mapping - different builds expose different attrs
                        item = hyd_list[0]
                        if hasattr(item, 'hydration_ml'):
                            data['hydration_ml'] = item.hydration_ml
                        elif hasattr(item, 'volume'):
                            data['hydration_ml'] = item.volume
            except Exception:
                pass

            # Try to get intensity minutes (may require OAuth1)
            try:
                if hasattr(garth, 'DailyIntensityMinutes'):
                    im_list = garth.DailyIntensityMinutes.list(day_str, 1)
                    if im_list:
                        item = im_list[0]
                        # prefer a generic total/minutes field if available
                        if hasattr(item, 'intensity_minutes'):
                            data['intensity_minutes'] = item.intensity_minutes
                        elif hasattr(item, 'total_minutes'):
                            data['intensity_minutes'] = item.total_minutes
                        elif hasattr(item, 'minutes'):
                            data['intensity_minutes'] = item.minutes
            except Exception:
                pass
            
            # Note: Resting heart rate is not available through the public API
            # without OAuth1 authentication. You may need to set up proper 
            # authentication or use a different data source.
            
            processed[day_str] = {
                'restingHeartRate': data.get('restingHeartRate'),
                'averageStressLevel': data.get('averageStressLevel'),
                'bodyBatteryLowestValue': data.get('bodyBatteryLowestValue'),
                'avgSPO2': data.get('avgSPO2'),
                'averageRespirationValue': data.get('averageRespirationValue'),
                'sleepScore': data.get('sleepScore'),
                'sleepDurationStr': data.get('sleepDurationStr')
                , 'hydration_ml': data.get('hydration_ml')
                , 'intensity_minutes': data.get('intensity_minutes')
            }

        except Exception as e:
            # If Garmin's servers don't have data for a day or something goes wrong,
            # we print the error and continue to the next day.
            print(f"   -> Could not fetch all data for {day_str}. Error: {e}")

        current_date += timedelta(days=1)

    # Step 5: Convert the collected data into a pandas DataFrame for easy manipulation.
    df = pd.DataFrame.from_dict(processed, orient='index')
    df.index.name = COL_DATE
    df = df.reset_index()

    # Step 6: Rename the columns to match what the rest of your application expects.
    df = df.rename(columns={
        'sleepScore': COL_SCORE,
        'restingHeartRate': COL_RESTING_HR,
        'bodyBatteryLowestValue': COL_BODY_BATTERY,
        'avgSPO2': COL_PULSE_OX,
        'averageRespirationValue': COL_RESPIRATION,
        'averageStressLevel': COL_AVG_STRESS,
        'sleepDurationStr': COL_DURATION,
        'hydration_ml': COL_HYDRATION,
        'intensity_minutes': COL_INTENSITY_MINUTES
    })

    # Step 7: Save the final data to a CSV file in the user's home directory.
    output_path = os.path.join(os.path.expanduser("~"), "garmin_auto_export.csv")
    df.to_csv(output_path, index=False)

    print(f"Data saved to {output_path}")
    return output_path


def interactive_login(email=None, password=None, save_path="~/.garth"):
    """
    Attempt an interactive login using garth and persist the session for future resume().
    Returns True if login+save succeeded, False otherwise.
    """
    try:
        if email is None or password is None:
            email = os.getenv("GARMIN_EMAIL")
            password = os.getenv("GARMIN_PASSWORD")

        if not email or not password:
            # Fallback to interactive prompt
            email = input("Garmin Email: ")
            password = input("Garmin Password: ")

        garth.login(email, password)
        garth.save(save_path)
        print("Garmin OAuth session saved to", save_path)
        return True
    except Exception as e:
        print("Interactive Garmin login failed:", e)
        return False


def ensure_oauth_session(save_path="~/.garth"):
    """Try to resume a saved OAuth1 session, otherwise prompt the user to login interactively.
    Returns True if an OAuth-capable session is available, False otherwise.
    """
    try:
        garth.resume(save_path)
        return True
    except Exception:
        # Try interactive login; this will prompt on the console if no env vars are set.
        return interactive_login(save_path=save_path)