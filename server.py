from flask import Flask, request, redirect, jsonify  # type: ignore
import requests
import json
import os
import gspread # type: ignore
from dotenv import load_dotenv  # type: ignore
from oauth2client.service_account import ServiceAccountCredentials # type: ignore

load_dotenv() # Load environment variables from .env file

app = Flask(__name__)

# Strava API credentials
CLIENT_ID = os.getenv("STRAVA_CLIENT_ID") # My Strava client ID
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET") # My Strava client ID
REDIRECT_URI = "https://testappstrava.onrender.com/callback"
GOOGLE_SHEET_NAME = "Athletes Strava" # Name of the google sheet where athlete data will be stored

# Google Sheets setup
GOOGLE_SHEET_NAME = "Athletes Strava" # Name of the google sheet where athlete data will be stored
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT") # Value of GOOGLE_SERVICE_ACCOUNT in .env file (or we can store it in Render also)
creds_dict = json.loads(SERVICE_ACCOUNT_JSON)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)


def save_to_google_sheets(athlete_id, athlete_info): # Each new athlete is added to the Google Sheets
    try:
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1

        records = sheet.get_all_records()
        existing_ids = [str(row['id']) for row in records]

        if athlete_id in existing_ids:
            print(f"Athlete {athlete_id} already in the Google Sheets.")
            return

        new_row = [
            athlete_id,
            athlete_info.get("firstname"),
            athlete_info.get("lastname"),
            athlete_info.get("access_token"),
            athlete_info.get("refresh_token")
        ]
        sheet.append_row(new_row)
        print("New athlete added to the Google Sheets.")

    except Exception as e:
        print(f"Error during the addition of the athlete to the Google Sheets : {e}")


@app.route("/")
def home():
    auth_url = (
        f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}&response_type=code"
        f"&approval_prompt=force&scope=activity:read_all"
    )
    return f"<h2>Authorize the access to your Strava account :</h2><a href='{auth_url}'>Click here</a>"


@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Error : no code received."

    token_url = "https://www.strava.com/oauth/token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code"
    }

    response = requests.post(token_url, data=payload).json()

    if "access_token" not in response:
        return "Error : Impossible to obtain the token."

    access_token = response["access_token"]
    refresh_token = response["refresh_token"]
    athlete = requests.get(
        "https://www.strava.com/api/v3/athlete",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()

    athlete_id = str(athlete["id"])
    athlete_info = {
        "firstname": athlete.get("firstname", "unknown"),
        "lastname": athlete.get("lastname", "unknown"),
        "access_token": access_token,
        "refresh_token": refresh_token
    }

    save_to_google_sheets(athlete_id, athlete_info)

    return f"{athlete_info['firstname']} {athlete_info['lastname']} added with success !"


# to execute the code in local
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
