# app.py
import streamlit as st
import pandas as pd
import requests
import os
import json
import subprocess
import sys
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
st.set_page_config(layout="wide")

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8501" # Must match your Strava API settings
ATHLETES_FILE_PATH = "src/athletes.json"

# --- AUTHENTICATION LOGIC ---

def display_login_button():
    """Displays the 'Connect with Strava' button."""
    auth_url = (
        f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}&response_type=code"
        f"&approval_prompt=force&scope=activity:read_all"
    )
    st.link_button("Connect with Strava", auth_url)

def handle_callback(code):
    """Exchanges the authorization code for an access token and saves athlete info."""
    try:
        # Exchange code for tokens
        token_url = "https://www.strava.com/oauth/token"
        payload = {
            "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
            "code": code, "grant_type": "authorization_code"
        }
        response = requests.post(token_url, data=payload).json()

        # Store key info in the session state for immediate use
        st.session_state['access_token'] = response['access_token']
        st.session_state['athlete_info'] = response['athlete']

        # --- Save/Update athlete info in athletes.json ---
        athlete_id = str(response['athlete']['id'])
        if os.path.exists(ATHLETES_FILE_PATH):
            with open(ATHLETES_FILE_PATH, "r") as f:
                data = json.load(f)
                athletes_dict = data.get("athletes", {})
        else:
            athletes_dict = {}
            
        athletes_dict[athlete_id] = {
            "firstname": response['athlete'].get("firstname"),
            "lastname": response['athlete'].get("lastname"),
            "access_token": response['access_token'],
            "refresh_token": response['refresh_token']
        }
        with open(ATHLETES_FILE_PATH, "w") as f:
            json.dump({"athletes": athletes_dict}, f, indent=4)
        
        return True # Indicate success
        
    except Exception as e:
        st.error(f"An error occurred during authentication: {e}")
        st.code(response.text) # Display raw error from Strava if available
        return False # Indicate failure

# --- MAIN APP LOGIC ---

st.title("🏃‍♂️ Strava Performance Dashboard")

# Step 1: Handle the authentication callback IF it's a new login
auth_code = st.query_params.get("code")
if auth_code and 'access_token' not in st.session_state:
    if handle_callback(auth_code):
        
        # --- TRIGGER DATA PROCESSING SCRIPTS ---
        st.info("✅ Authentication successful! Fetching your Strava data. This may take several minutes...")

        try:
            # Display progress messages to the user
            progress_text = st.empty()

            # Step 1.A: Run the data fetching script
            progress_text.write("Étape 1/2 : Téléchargement des activités...")
            # Use sys.executable to ensure we're using the same python interpreter from the venv
            # capture_output and text=True are useful for debugging
            fetch_process = subprocess.run(
                [sys.executable, "src/fetch_activities.py"], 
                check=True, capture_output=True, text=True
            )

            # Step 1.B: Run the feature building script
            progress_text.write("Étape 2/2 : Traitement des activités et calcul des statistiques...")
            build_process = subprocess.run(
                [sys.executable, "src/build_features.py"], 
                check=True, capture_output=True, text=True
            )
            
            progress_text.success("🚀 Your data is ready! Displaying the dashboard.")
            
        except subprocess.CalledProcessError as e:
            # If a script fails, show a helpful error message
            st.error("An error occurred while processing your data. Please try again later.")
            st.subheader("Error details:")
            st.code(e.stderr) # Display the error output from the failed script
        
        # Clean the URL by clearing the query parameters
        st.query_params.clear()
        st.button("Afficher mon dashboard") # Add a button to force a final rerun and display the data

# Step 2: Display the dashboard OR the login button based on the session state
if 'access_token' in st.session_state:
    # --- This is the main dashboard ---
    st.header("Welcome!")
    athlete_name = st.session_state['athlete_info']['firstname']
    st.write(f"Hello, {athlete_name}! Here's a preview of your data:")
    
    try:
        master_file_path = "data/processed/activities_master.csv"
        df_master = pd.read_csv(master_file_path, parse_dates=['start_date'])
        
        # You can now filter the dataframe for the logged-in user
        athlete_id = st.session_state['athlete_info']['id']
        df_athlete = df_master[df_master['athlete_id'] == athlete_id]
        
        if df_athlete.empty:
            st.warning("We couldn't find any processed activities for you. Maybe the initial data sync is still in progress?")
        else:
            st.subheader("Your Latest Activities")
            st.dataframe(df_athlete.tail(10))

            st.subheader("Your Training Load Over Time")
            df_athlete = df_athlete.sort_values(by="start_date")
            st.line_chart(df_athlete, x='start_date', y='training_load')

    except FileNotFoundError:
        st.warning("Processed data file not found. Please connect your account to generate it.")
    except Exception as e:
        st.error(f"An error occurred while loading data: {e}")

else:
    # --- This is the login page ---
    st.write("Click the button below to connect your Strava account and see your stats.")
    display_login_button()