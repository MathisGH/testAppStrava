import requests
import pandas as pd
import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv # type: ignore
load_dotenv() # Load environment variables from the .env file

import gspread # The script will directly read the tokens from the Google Sheet 
from oauth2client.service_account import ServiceAccountCredentials

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


SCRIPT_DIR = Path(__file__).resolve().parent
ATHLETES_FILE = SCRIPT_DIR / "athletes.json" # JSON where athlete info will be stored (id, name, access and refresh token)
DATA_FOLDER = SCRIPT_DIR.parent / "data" / "raw" # in which fetched activities will be stored
AUTH_URL = "https://www.strava.com/oauth/token" # URL in order to refresh the access token
ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities" # URL in order to fetch activities from an athlete
ACTIVITY_DETAILS_URL = "https://www.strava.com/api/v3/activities/" # URL in order to fetch the details of an activity
CLIENT_ID = os.getenv("STRAVA_CLIENT_ID") # get the Strava Client ID from the .env file
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET") # get the Strava secret token from the .env file

os.makedirs(DATA_FOLDER, exist_ok=True)  # If the folder doesn't exist yet, create it

def load_athletes(): # Load athletes DIRECTLY FROM GOOGLE SHEETS
    """Connects to Google Sheets and fetches athlete data."""
    try:
        # Google Sheets Authentication
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        SERVICE_ACCOUNT_JSON_STR = os.getenv("GOOGLE_SERVICE_ACCOUNT")
        creds_dict = json.loads(SERVICE_ACCOUNT_JSON_STR)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # Fetching data from the specified Google Sheet (my sheet name is "Athletes Strava")
        sheet = client.open("Athletes Strava").sheet1
        records = sheet.get_all_records()

        # Converting to the format used in the rest of the app
        athletes_dict = {}
        for row in records:
            athlete_id = str(row['id'])
            athletes_dict[athlete_id] = {
                "firstname": row.get("firstname"),
                "lastname": row.get("lastname"),
                "access_token": row.get("access_token"),
                "refresh_token": row.get("refresh_token")
            }
        return athletes_dict
        
    except Exception as e:
        print(f"Error loading athletes from Google Sheets: {e}")
        return {}


def refresh_token(athlete): # Access token refresh
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": athlete["refresh_token"],
        "grant_type": "refresh_token"
    }
    res = requests.post(AUTH_URL, data=payload).json()
    athlete["access_token"] = res.get("access_token", athlete["access_token"])
    athlete["refresh_token"] = res.get("refresh_token", athlete["refresh_token"])
    return athlete

def fetch_activities(): # Main function to fetch activities for each athlete in the JSON file
    athletes = load_athletes()
    
    for athlete_id, athlete in athletes.items():
        logging.info(f"Fetching activities for {athlete['firstname']} {athlete['lastname']}")
        # print(f"Fetching activities for {athlete['firstname']} {athlete['lastname']}") # Print version
        
        # Refresh the token
        athlete = refresh_token(athlete)

        headers = {'Authorization': f'Bearer {athlete["access_token"]}'}
        file_path = os.path.join(DATA_FOLDER, f"activities_{athlete_id}_{athlete['firstname']}_{athlete['lastname']}.csv")
        
        # Load existing activities
        if os.path.exists(file_path):
            df_existing = pd.read_csv(file_path)
            existing_ids = set(df_existing['id'].astype(str))
        else:
            df_existing = pd.DataFrame()
            existing_ids = set()

        # Fetch new activities
        request_page_num = 1
        new_activities = []

        while True:
            params = {'per_page': 200, 'page': request_page_num}
            response = requests.get(ACTIVITIES_URL, headers=headers, params=params).json()

            if not response:
                break

            new_data = [activity for activity in response if str(activity['id']) not in existing_ids]
            if not new_data:
                break

            new_activities.extend(new_data)
            request_page_num += 1
            logging.info(f"Page {request_page_num} fetched: ({len(new_data)} new activities)")
            # print(f"Page {request_page_num} fetched: ({len(new_data)} new activities)")

            # Stop the loop if we reach the quota and wait 15 minutes
            if request_page_num % 290 == 0:
                logging.warning("API limit reached, sleeping 15 minutes...")
                # print("API limit reached, sleeping 15 minutes...")
                time.sleep(900)

        # Fetch details of new activities
        detailed_activities = []
        for activity in new_activities:
            activity_id = activity['id']
            details = requests.get(f"{ACTIVITY_DETAILS_URL}{activity_id}", headers=headers).json()
            activity.update(details)
            detailed_activities.append(activity)
            logging.info(f"Details fetched for activity {activity_id}")
            # print(f"Details fetched for activity {activity_id}")
            time.sleep(1)  # Pause to respect the quotas

        # CSV update
        if detailed_activities:
            df_new = pd.DataFrame(detailed_activities)
            df_final = pd.concat([df_existing, df_new], ignore_index=True)
            full_id = f"{athlete_id}_{athlete['firstname']}_{athlete['lastname']}"
            df_final["athlete_id"] = full_id
            df_final.to_csv(file_path, index=False)
            logging.info(f"{len(detailed_activities)} new activities saved for {athlete['firstname']}")
            # print(f"{len(detailed_activities)} new activities saved for {athlete['firstname']}")

if __name__ == "__main__":
    fetch_activities()