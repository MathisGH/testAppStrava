import streamlit as st
import pandas as pd
import requests
import os
import json
import subprocess
import sys
import gspread
import joblib
import plotly.graph_objects as go
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from pathlib import Path
import altair as alt

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

# --- CONFIGURATION ---
load_dotenv()
st.set_page_config(layout="wide")

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REDIRECT_URI = os.getenv("STRAVA_REDIRECT_URL")
GOOGLE_SHEET_NAME = "Athletes Strava"

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_FILE = "/home/ec2-user/strava-app/testAppStrava/creds.json"
if os.path.exists(SERVICE_ACCOUNT_FILE):
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    gspread_client = gspread.authorize(creds)
    sheet = gspread_client.open(GOOGLE_SHEET_NAME).sheet1
else:
    sheet = None
    st.warning("Google credentials file not found. Please check creds.json")

# --- CLUSTERING ---

@st.cache_resource
def load_models():
    scaler = joblib.load("models/scaler.pkl")
    kmeans = joblib.load("models/kmeans.pkl")
    return scaler, kmeans

@st.cache_data
def load_cluster_labels():
    try:
        with open("models/cluster_labels.json", "r") as f:
            labels = json.load(f)
    except:
        labels = {}
    return labels

scaler, kmeans = load_models()
cluster_labels = load_cluster_labels()

# --- STRAVA AUTHENTICATION LOGIC ---

def display_login_button():
    """'Connect with Strava' button"""
    auth_url = (
        f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}&response_type=code"
        f"&approval_prompt=force&scope=activity:read_all"
    )
    st.link_button("Connect with Strava", auth_url)


def save_to_google_sheets(athlete_id, athlete_info):
    """Save athlete credentials to Google Sheets (only once)"""
    try:
        if not sheet:
            st.error("Google Sheets not configured. Maybe check GOOGLE_SERVICE_ACCOUNT in .env")
            return

        records = sheet.get_all_records()
        existing_ids = [str(row['id']) for row in records]

        if athlete_id in existing_ids:
            st.info(f"Athlete {athlete_id} already exists in Google Sheets")
            return

        new_row = [
            athlete_id,
            athlete_info.get("firstname"),
            athlete_info.get("lastname"),
            athlete_info.get("access_token"),
            athlete_info.get("refresh_token"),
        ]
        sheet.append_row(new_row)
        st.success(f"Athlete {athlete_info['firstname']} added to Google Sheets")

    except Exception as e:
        st.error(f"Error saving to Google Sheets: {e}")


def handle_callback(code):
    """Exchanges the authorization code for an access token and saves athlete info"""
    try:
        # Exchange code for tokens
        token_url = "https://www.strava.com/oauth/token"
        payload = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code"
        }
        response = requests.post(token_url, data=payload).json()

        if "access_token" not in response:
            st.error(f"Authentication failed: {response}")
            return False

        st.session_state['access_token'] = response['access_token']
        st.session_state['athlete_info'] = response['athlete']

        # Save athlete to Google Sheets
        athlete_id = str(response['athlete']['id'])
        athlete_info = {
            "firstname": response['athlete'].get("firstname"),
            "lastname": response['athlete'].get("lastname"),
            "access_token": response['access_token'],
            "refresh_token": response['refresh_token'],
        }
        save_to_google_sheets(athlete_id, athlete_info)

        return True

    except Exception as e:
        st.error(f"An error occurred during authentication: {e}")
        return False

# --- ACWR ---
def interpret_acwr(acwr):
    if acwr < 0.8:
        return "🔵 Training load lower than usual -> Good for recovery, but long-term progression might slow down"
    elif 0.8 <= acwr <= 1.3:
        return "🟢 Optimal training load"
    elif 1.3 < acwr <= 1.5:
        return "🟠 Slightly high workload -> Pay attention to fatigue signs"
    else:
        return "🔴 High workload -> Risk of injury"

def create_acwr_gauge(acwr_value, previous_value=None):
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=acwr_value,
        title={'text': "Current training status", 'font': {'size': 20}},
        delta={'reference': previous_value, 'increasing': {'color': "OrangeRed"}, 'decreasing': {'color': "Green"}},
        gauge={
            'axis': {'range': [0, 2.3], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': "darkblue"}, 
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            # Color threshold
            'steps': [
                {'range': [0, 0.8], 'color': 'lightblue'},      # Under training
                {'range': [0.8, 1.3], 'color': 'green'},   # Optimal zone
                {'range': [1.3, 1.5], 'color': 'orange'},       # Caution zone
                {'range': [1.5, 2.5], 'color': 'red'}    # Over training (danger)
            ],
            # Red line for the threshold
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 1.5
            }
        }
    ))
    fig.update_layout(height=st.session_state.get("gauge_height", 380), margin={'t':30, 'b':30, 'l':30, 'r':30}) # height responsive
    return fig


# --- MAIN APP ---

# --- PAGE TITLE ---
st.title("Strava Performance Dashboard")

# --- SIDEBAR ---
st.sidebar.title("Filters & Settings")
st.sidebar.write("Use the filters below to customize your dashboard")
activity_type = st.sidebar.multiselect(
    "Select Activity Types",
    options=["Run", "Ride", "Swim", "Workout", "Hike"],
    default=["Run"]
)

# Handle the authentication callback IF it's a new login
auth_code = st.query_params.get("code")
if auth_code and 'access_token' not in st.session_state:
    if handle_callback(auth_code):
        st.info("Authentication successful! Fetching your Strava data. This may take several minutes...")

        try:
            progress_text = st.empty()

            progress_text.write("Step 1/2 : Downloading activities...")
            subprocess.run(
                [sys.executable, "src/fetch_activities.py"],
                check=True, capture_output=True, text=True
            )

            progress_text.write("Step 2/2 : Process activities and compute features...")
            subprocess.run(
                [sys.executable, "src/build_features.py"],
                check=True, capture_output=True, text=True
            )

            progress_text.success("Your data is ready! Displaying the dashboard")

        except subprocess.CalledProcessError as e:
            st.error("An error occurred while processing your data")
            st.code(e.stderr)

        st.query_params.clear()

# --- MAIN DASHBOARD ---
if 'access_token' in st.session_state:
    st.header("Welcome!")
    athlete_name = st.session_state['athlete_info']['firstname']
    st.write(f"Hello, {athlete_name}, here's a preview of your data:")

    athletes_summary_path = "data/processed/athletes_summary.csv"
    athletes_summary = pd.read_csv(athletes_summary_path)

    try:
        master_file_path = "data/processed/activities_master.csv"
        df_master = pd.read_csv(master_file_path, parse_dates=['start_date'])

        athlete_id = st.session_state['athlete_info']['id']
        df_athlete_full = df_master[(df_master['athlete_id'] == athlete_id) & (df_master['sport_type'].isin(activity_type))]

        if df_athlete_full.empty:
            st.warning("We couldn't find any processed activities for you yet.")
        else:
            left, right = st.columns(2)
            # Left column
            with left: # Left column
                st.write("### Your current training status (ACWR)")
                df_sorted = df_athlete_full.sort_values('start_date', ascending=False)
                
                latest_acwr = df_sorted['acwr'].iloc[0] if not df_sorted.empty else 0
                previous_acwr = df_sorted['acwr'].iloc[1] if len(df_sorted) > 1 else latest_acwr

                fig_gauge = create_acwr_gauge(latest_acwr, previous_acwr)
                st.plotly_chart(fig_gauge, use_container_width=True)

                # Interpretation text
                interpretation = interpret_acwr(latest_acwr)
                st.markdown(f"**Interpretation:** {interpretation}")

                # Mini explanation of ACWR
                with st.expander("What is ACWR?"):
                    st.write("""
            **ACWR (Acute : Chronic Workload Ratio)** compares:
            - **Acute load (7 days)** → the short-term training load  
            - **Chronic load (28 days)** → what your body is used to  

            It helps balance progression and injury risk.  
            The target zone is **0.8 to 1.3**.
                    """)
            
            # Right column
            with right:
                st.write("### HR Zones Distribution (last 60 days)")
                latest = df_sorted.iloc[0]

                zones = pd.DataFrame({
                    "zone": ["Z1", "Z2", "Z3", "Z4"],
                    "percentage": [
                        latest["pct_time_Z1_last_60d"],
                        latest["pct_time_Z2_last_60d"],
                        latest["pct_time_Z3_last_60d"],
                        latest["pct_time_Z4_last_60d"],
                    ]
                })

                chart = (
                    alt.Chart(zones)
                    .mark_arc()
                    .encode(
                        theta="percentage",
                        color="zone",
                        tooltip=["zone", "percentage"]
                    )
                )
                st.altair_chart(chart, use_container_width=True)

                # Heartrate zones explanation
                with st.expander("More about your HR Zones"):
                    athlete_id = latest["athlete_id"]

                    # Retrieve max HR from athletes_summary
                    df_athlete = athletes_summary[athletes_summary["athlete_id"] == athlete_id]

                    if df_athlete.empty:
                        st.write("No athlete summary available.")
                    else:
                        max_hr = df_athlete.iloc[0]["max_hr"]

                        if pd.isna(max_hr) or max_hr == 0:
                            st.write("Max HR not available for this athlete.")
                        else:
                            zones_bpm = {
                                "Z1": (0, int(max_hr * 0.78)),
                                "Z2": (int(max_hr * 0.78), int(max_hr * 0.84)),
                                "Z3": (int(max_hr * 0.84), int(max_hr * 0.92)),
                                "Z4": (int(max_hr * 0.92), max_hr)
                            }

                            # Short descriptions
                            zone_desc = {
                                "Z1": "Easy / Recovery",
                                "Z2": "Endurance Aerobic",
                                "Z3": "Threshold / Tempo",
                                "Z4": "High intensity"
                            }

                            st.write(f"**Max HR detected:** {max_hr} bpm")

                            # Display table of zones
                            st.write("### Your personalized HR zones")
                            for zone, (low, high) in zones_bpm.items():
                                st.write(
                                    f"**{zone} ({low}–{high} bpm)** — {zone_desc[zone]}"
                                )
                    

            # --- LAST 10 ACTIVITIES START --- 

            # Clusters
            CLUSTER_COLORS = {
                0: "green",   # Endurance
                1: "yellow",  # Threshold
                2: "red",     # Intensity
                3: "blue",    # Long run
            }

            CLUSTER_LABELS = {
                0: "Endurance",
                1: "Threshold",
                2: "Intensity",
                3: "Long run",
            }

            master_file_path = "data/processed/activities_master_with_clusters.csv"
            df_master = pd.read_csv(master_file_path, parse_dates=['start_date'])
            df_sample = df_master[(df_master["athlete_id"]==athlete_id) & (df_master["sport_type"].isin(activity_type))].sort_values(by='start_date', ascending=False)

            st.subheader("Your last 10 activities:")

            for _, row in df_sample.head(10).iterrows():
                cluster = int(row["cluster"])
                label = CLUSTER_LABELS.get(cluster, "Unknown")

                col1, col2 = st.columns([4, 1])

                with col1:
                    st.write(
                        f"**{row['sport_type']} — {row['start_date'].date()}**  "
                        f"| {row['distance_activity']/1000:.1f} km  "
                        f"| {row['moving_time_activity']/60:.1f} hours"
                    )

                with col2:
                    st.badge(label, color=CLUSTER_COLORS.get(cluster, "gray"))

                with st.expander("Show details"):

                    left, right = st.columns(2)

                    # Left column
                    with left: # Left column
                        st.write(f"**Distance:** {row['distance_activity']/1000:.1f} km")
                        st.write(f"**Duration:** {row['moving_time_activity']/60:.1f} hours")
                        st.write(f"**Elevation:** {row['elevation_gain_activity']} m")
                        st.write(f"**Avg Pace:** {60 / row['average_speed_km_h_activity']:.1f} min/km")
                        st.write(f"**Training Load:** {row['training_load']:.1f}")
                        st.write(f"**Average Heartrate:** {row['average_heartrate_activity']:.1f}")
                        st.write(f"**Activity type:** {row['cluster']:.1f}")
                    
                    # Right column
                    with right:
                        st.write("### HR Zones")
                        zones = pd.DataFrame({
                            "zone": ["Z1", "Z2", "Z3", "Z4"],
                            "minutes": [
                                row["pct_Z1"]*row["moving_time_activity"], 
                                row["pct_Z2"]*row["moving_time_activity"], 
                                row["pct_Z3"]*row["moving_time_activity"], 
                                row["pct_Z4"]*row["moving_time_activity"]
                            ]
                        })

                        chart = (
                            alt.Chart(zones)
                            .mark_arc()
                            .encode(
                                theta="minutes",
                                color="zone",
                                tooltip=["zone", "minutes"]
                            )
                        )
                        st.altair_chart(chart, use_container_width=True)

            # --- LAST 10 ACTIVITIES END ---

            # st.subheader("Your Latest Activities")
            df_athlete_display = df_athlete_full.sort_values(by="start_date", ascending=False).drop_duplicates(subset=["activity_id"])

            columns_to_show = ["sport_type", "distance_activity", "moving_time_activity", "elevation_gain_activity", "average_speed_km_h_activity", "average_heartrate_activity", "training_load", "start_date"]
            # st.dataframe(df_athlete_display[columns_to_show].head(10))

            st.subheader("Your cumulative training load over the last 4 weeks")
            st.line_chart(df_athlete_display, x='start_date', y='cumulative_training_load_4_weeks')


            # --- ATHLETES STATS START ---
            st.write("## Athlete Summary")
            athlete_id = latest["athlete_id"]
            df_athlete = athletes_summary[athletes_summary["athlete_id"] == athlete_id]

            if df_athlete.empty:
                st.write("No athlete summary available.")
            else:
                row = df_athlete.iloc[0]

                st.write("### General statistics")

                col1, col2 = st.columns(2)

                with col1:
                    st.metric("Total Runs", int(row["Nb_activities_run"]))
                    st.metric("Total Rides", int(row["Nb_activities_ride"]))
                    st.metric("Total Workouts", int(row["Nb_activities_workout"]))

                with col2:
                    st.metric("Distance Run", f"{int(row['Total_distance_run'])/1000} km")
                    st.metric("Distance Ride", f"{int(row['Total_distance_ride'])/1000} km")
                    st.metric("Max HR", int(row["max_hr"]))

                st.write("---")
                st.write("### Best Performances (PBs)")
                
                pb_cols = ["PB_5km", "PB_10km", "PB_21.1km", "PB_42.2km"]
                for pb in pb_cols:
                    if not pd.isna(row[pb]):
                        st.write(f"**{pb.replace('PB_', '')}:** {row[pb]}")

                st.write("---")
                # --- ATHLETES STATS END ---


    except FileNotFoundError:
        st.warning("Processed data file not found. Please connect your account first.")
    except Exception as e:
        st.error(f"Error loading data: {e}")

else:
    st.write("Click below to connect your Strava account:")
    display_login_button()