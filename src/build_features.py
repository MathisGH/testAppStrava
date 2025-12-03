import pandas as pd
import numpy as np
import os
import ast
import warnings
import math
import time
from pathlib import Path
from dotenv import load_dotenv # type: ignore
from sqlalchemy import create_engine
import requests
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- CONFIGURATION & INITIALIZATION ---
load_dotenv()  # Load environment variables from .env file
warnings.filterwarnings("ignore", category=DeprecationWarning)

password_sql = os.getenv("POSTGRES_PASSWORD")
# For GCP
# engine = create_engine(f"postgresql://postgres:{password_sql}@localhost:5432/strava_db")

# --- DATA LOADING FUNCTIONS ---

def load_data(filepath: Path) -> pd.DataFrame:
    """Load all CSV files from the given directory into a single DataFrame"""
    df = pd.concat(
        [pd.read_csv(os.path.join(filepath, f)) for f in os.listdir(filepath) if f.endswith(".csv")],
        ignore_index=True
    )
    return df

# --- DATA CLEANING & PREPROCESSING FUNCTIONS ---

def clean_activities(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean and preprocess the main activity DataFrame, including cumulative distances and splits"""
    keep_cols = [
        'athlete', 'distance', 'moving_time', 'total_elevation_gain', 'sport_type', 'id',
        'start_date', 'average_speed', 'max_speed', 'average_watts', 'average_heartrate',
        'max_heartrate', 'splits_metric', 'best_efforts', 'athlete_id',
        'max_watts', 'weighted_average_watts', 'start_latlng'
    ]
    df = df[keep_cols]

    # Process athlete ID
    df['athlete'] = df['athlete'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
    df['athlete_id'] = df['athlete'].apply(lambda x: x['id'] if isinstance(x, dict) else None)
    df = df.drop(columns=['athlete'])

    df = df.rename(columns={'id': 'activity_id'})

    # Convert times and speeds
    df['moving_time'] = round(df['moving_time'] / 60, 2)  # minutes
    df['average_speed_km_h'] = round(df['average_speed'] * 3.6, 2)
    df['max_speed_km_h_activity'] = round(df['max_speed'] * 3.6, 2)
    df = df.drop(columns=["average_speed", 'max_speed'])

    df['start_date'] = pd.to_datetime(df['start_date'])

    # Rename columns for clarity
    df = df.rename(columns={
        'distance': 'distance_activity',
        'moving_time': 'moving_time_activity',
        'average_speed_km_h': 'average_speed_km_h_activity',
        'average_heartrate': 'average_heartrate_activity',
        'total_elevation_gain': 'elevation_gain_activity',
        'max_heartrate': 'max_heartrate_activity',
        'average_watts': 'average_watts_activity',
        'max_watts': 'max_watts_activity',
        'weighted_average_watts': 'weighted_average_watts_activity'
    })

    # Sort for cumulative distance computation
    df = df.sort_values(by=['athlete_id', 'start_date'])

    # Compute cumulative distance by sport
    def cumulative_distance(df, sport):
        return (
            df[df['sport_type'] == sport]
            .groupby('athlete_id')['distance_activity']
            .cumsum()
            .reindex(df.index)
        )


    df['cumulative_distance_run'] = cumulative_distance(df, 'Run')
    df['cumulative_distance_ride'] = cumulative_distance(df, 'Ride')
    df['cumulative_distance_swim'] = cumulative_distance(df, 'Swim')

    # Explode and flatten splits
    df_with_splits = df.copy()
    df_with_splits['splits_metric'] = df_with_splits['splits_metric'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
    df_splits_metric = df_with_splits.explode("splits_metric").reset_index(drop=True)
    df_splits_metric = pd.concat(
        [df_splits_metric.drop(columns=["splits_metric"]), df_splits_metric["splits_metric"].apply(pd.Series)],
        axis=1
    )
    
    # Return the cleaned main dataframe and the exploded splits dataframe
    return df, df_splits_metric

def process_best_efforts(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Extract and process best effort data and create the final splits DataFrame"""
    df_clean, df_splits_metric = clean_activities(df.copy())

    # Process best efforts
    df_clean['best_efforts'] = df_clean['best_efforts'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
    df_efforts = df_clean[df_clean['best_efforts'].apply(lambda x: isinstance(x, list) and len(x) > 0)].copy()
    df_best_efforts = df_efforts.explode("best_efforts").reset_index(drop=True)

    df_best_efforts = pd.concat(
        [df_best_efforts.drop(columns=["best_efforts", 'start_date']),
         df_best_efforts["best_efforts"].apply(pd.Series)],
        axis=1
    )
    df_best_efforts['elapsed_time_best_effort_min'] = df_best_efforts['elapsed_time'] / 60
    df_best_efforts = df_best_efforts.rename(columns={
        'name': 'best_effort_name',
        'elapsed_time': 'elapsed_time_best_effort',
        'distance': 'distance_best_effort'
    })
    
    df_best_efforts = df_best_efforts.dropna(subset=['pr_rank'])
    keep_cols_best_efforts = [
        'distance_activity', 'moving_time_activity', 'elevation_gain_activity', 'sport_type',
        'activity_id', 'athlete_id', 'id', 'best_effort_name', 'moving_time',
        'start_date', 'distance_best_effort', 'pr_rank'
    ]
    keep_cols_best_efforts = [col for col in keep_cols_best_efforts if col in df_best_efforts.columns]
    df_best_efforts = df_best_efforts[keep_cols_best_efforts]
    
    df_best_efforts['start_date'] = pd.to_datetime(df_best_efforts['start_date'])
    df_best_efforts['moving_time'] = round(df_best_efforts['moving_time'] / 60, 2)
    df_best_efforts = df_best_efforts[~df_best_efforts['best_effort_name'].isin(
        ['2 mile', '1/2 mile', '10 mile', '1K', '400m', '15K', '1 mile']
    )]

    # Process splits dataframe to create the final version
    df_splits_metric['start_date'] = pd.to_datetime(df_splits_metric['start_date'])
    df_splits_metric['average_speed_km_h'] = df_splits_metric['average_speed'] * 3.6
    df_splits_metric = df_splits_metric.rename(columns={
        'distance': 'distance_split',
        'moving_time': 'moving_time_split',
        'average_speed': 'average_speed_split',
        'average_speed_km_h': 'average_speed_km_h_split',
        'average_heartrate': 'average_heartrate_split'
    })
    df_splits_metric = df_splits_metric.drop(columns=[
        'elapsed_time', 0, 'average_grade_adjusted_speed',
        'pace_zone', 'split', 'best_efforts'
    ], errors='ignore')

    return df_best_efforts, df_splits_metric

# --- ADDING WEATHER DATA USING OPEN METEO API ---

def get_weather_for_activity(activity_row):
    """
    Fetch weather data for a given activity using Open-Meteo API
    Every activity_row must have 'start_date' (datetime) and 'start_latlng' (string like '[lat, lon]')
    """
    # 1. Extract latitude and longitude
    try:
        coords = ast.literal_eval(activity_row["start_latlng"])
        lat, lon = coords[0], coords[1]
    except (ValueError, SyntaxError, TypeError, IndexError):
        return pd.Series({'temperature': None, 'humidity': None, 'apparent_temperature': None, 'precipitation': None, 'wind_speed': None})
    
    # Ensure start_date is datetime
    activity_date = pd.to_datetime(activity_row['start_date'])

    # 2. Prepare API request
    API_URL = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        'latitude': lat,
        'longitude': lon,
        'start_date': activity_date.strftime('%Y-%m-%d'),
        'end_date': activity_date.strftime('%Y-%m-%d'),
        'hourly': 'temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,windspeed_10m',
        'timezone': 'auto'
    }

    # 3. Call the API
    try:
        response = requests.get(API_URL, params=params)
        response.raise_for_status()

        data = response.json()

        hourly_data = data['hourly']
        activity_hour_index = activity_date.hour

        temp = hourly_data['temperature_2m'][activity_hour_index]
        humidity = hourly_data['relative_humidity_2m'][activity_hour_index]
        apparent_temp = hourly_data['apparent_temperature'][activity_hour_index]
        precip = hourly_data['precipitation'][activity_hour_index]
        wind = hourly_data['windspeed_10m'][activity_hour_index]

        return pd.Series({
            'temperature': temp, 
            'humidity': humidity, 
            'apparent_temperature': apparent_temp, 
            'precipitation': precip, 
            'wind_speed': wind
        })
    except requests.exceptions.RequestException as e:
        logging.error(f"API error for activity {activity_row.get('activity_id', 'unknown')}: {e}")
        # print(f"Erreur API pour l'activité {activity_row.get('activity_id', 'unknown')}: {e}")
        return pd.Series({'temperature': None, 'humidity': None, 'apparent_temperature': None, 'precipitation': None, 'wind_speed': None})



# --- FEATURE ENGINEERING FUNCTIONS ---

def vdot_to_speed(vdot):
    a = 0.000104
    b = 0.182258
    c = -4.6 - vdot
    discriminant = b**2 - 4*a*c
    if discriminant < 0:
        return None
    v_m_per_min = (-b + math.sqrt(discriminant)) / (2*a)
    v_kmh = (v_m_per_min * 60) / 1000
    return v_kmh

def extract_best_effort_time(df_best_efforts, distance_km):
    return (
        df_best_efforts[
            df_best_efforts['distance_best_effort'].between((distance_km - 0.2)*1000, (distance_km + 0.2)*1000)
        ].groupby('athlete_id')['moving_time'].min().round(2)
    )

def calculate_vdot(distance_m, time_sec):
    """Estimate VDOT score based on distance and time"""
    if time_sec is None or time_sec == 0:
        return None
    time_min = time_sec / 60
    
    velocity = distance_m / time_min  # m/min
    vo2 = -4.6 + 0.182258 * velocity + 0.000104 * velocity**2
    percent_max = 0.8 + 0.1894393 * math.exp(-0.012778 * time_min) + 0.2989558 * math.exp(-0.1932605 * time_min)
    return round(vo2 / percent_max, 2)

def process_splits(splits_df, max_hr_dict):
    """Analyze split-level HR and speed variability and aggregate per activity"""
    splits_df = splits_df.copy()

    def get_hr_zone(hr, max_hr):
        if pd.isna(hr) or pd.isna(max_hr) or max_hr == 0:
            return np.nan
        ratio = round(hr / max_hr, 4)
        if ratio < 0.78: return "Z1"
        elif 0.78 <= ratio < 0.84: return "Z2"
        elif 0.84 <= ratio < 0.92: return "Z3"
        else: return "Z4"

    splits_df["max_hr"] = splits_df["athlete_id"].map(max_hr_dict)
    splits_df["hr_zone"] = splits_df.apply(lambda row: get_hr_zone(row["average_heartrate_split"], row["max_hr"]), axis=1)

    results = []
    for activity_id, group in splits_df.groupby("activity_id"):
        mean_speed = group["average_speed_km_h_split"].mean()
        cv_speed = round((group["average_speed_km_h_split"].std() / mean_speed), 5) if mean_speed != 0 else 0 # Ensure mean is not zero to avoid division by zero
        
        zone_pct = group["hr_zone"].value_counts(normalize=True).reindex(["Z1", "Z2", "Z3", "Z4"], fill_value=0)
        zone_pct.index = [f"pct_{z}" for z in zone_pct.index]
        res = {"activity_id": activity_id, "cv_speed": cv_speed}
        res.update(zone_pct.to_dict())
        results.append(res)

    return pd.DataFrame(results)

def generate_athlete_stats(df_clean, df_best_efforts, manual_stats_path):
    """Compute athlete-level stats using df_clean (for max_hr, totals) and df_best_efforts"""
    unique_athletes = df_clean['athlete_id'].unique()
    df_athletes_summary = pd.DataFrame({'athlete_id': unique_athletes})

    # Number of activities
    for sport in ['Run', 'Ride', 'Swim', 'Workout']:
        counts = df_clean[df_clean['sport_type'] == sport].groupby('athlete_id')['activity_id'].nunique()
        df_athletes_summary = df_athletes_summary.merge(counts.rename(f'Nb_activities_{sport.lower()}'), on='athlete_id', how='left')

    # Total distances
    distances = {
        'Total_distance_run': df_clean[df_clean['sport_type'] == 'Run'].groupby('athlete_id')['distance_activity'].sum(),
        'Total_distance_ride': df_clean[df_clean['sport_type'] == 'Ride'].groupby('athlete_id')['distance_activity'].sum(),
        'Total_distance_swim': df_clean[df_clean['sport_type'] == 'Swim'].groupby('athlete_id')['distance_activity'].sum()
    }
    for k, v in distances.items():
        df_athletes_summary = df_athletes_summary.merge(v.rename(k), on='athlete_id', how='left')

    # max_hr from df_clean
    fc_valid = df_clean[(df_clean['max_heartrate_activity'] < 210) & (df_clean['max_heartrate_activity'] > 100)]
    max_hr = fc_valid.groupby('athlete_id')['max_heartrate_activity'].apply(lambda x: x.nlargest(5).mean()).round()
    df_athletes_summary = df_athletes_summary.merge(max_hr.rename('max_hr'), on='athlete_id', how='left')

    # Best efforts
    for dist_km in [5, 10, 21.1, 42.2]:
        dist_km_float = float(dist_km)
        clean_dist = int(dist_km_float) if dist_km_float.is_integer() else dist_km_float
        col_name = f"PB_{clean_dist}km"

        pb_times = extract_best_effort_time(df_best_efforts, dist_km)
        df_athletes_summary = df_athletes_summary.merge(pb_times.rename(col_name), on='athlete_id', how='left')

    # Merge manual stats
    if Path(manual_stats_path).exists():
        manual_stats = pd.read_csv(manual_stats_path)
        df_athletes_summary = df_athletes_summary.merge(manual_stats, on='athlete_id', how='left', suffixes=('', '_manual'))
        # Prioritize calculated values but fill NaNs with manual values
        for col in manual_stats.columns:
            if col != 'athlete_id' and f'{col}_manual' in df_athletes_summary.columns:
                df_athletes_summary[col] = df_athletes_summary[col].fillna(df_athletes_summary[f'{col}_manual'])
                df_athletes_summary = df_athletes_summary.drop(columns=[f'{col}_manual'])
                
    df_athletes_summary = df_athletes_summary.fillna(0)
    activity_cols = [col for col in df_athletes_summary.columns if 'Nb_activities' in col]
    df_athletes_summary['Nb_activities'] = df_athletes_summary[activity_cols].sum(axis=1)

    # VDOT estimation
    for dist_m, label in [(5000, 'PB_5km'), (10000, 'PB_10km'), (21097, 'PB_21.1km'), (42195, 'PB_42.2km')]:
        vdot_col = f'VDOT_{label.split("_")[0]}'
        df_athletes_summary[vdot_col] = df_athletes_summary.apply(
            lambda row: calculate_vdot(dist_m, row[label]*60) if row[label] > 0 else None, axis=1)

    vdot_cols = [col for col in df_athletes_summary.columns if 'VDOT' in col]
    df_athletes_summary['VDOT_max'] = df_athletes_summary[vdot_cols].max(axis=1)

    return df_athletes_summary


def build_activity_master(df_clean, df_split_features, df_athletes_summary_new):
    """
    Merge cleaned activity data with split-based features
    and compute final activity-level metrics
    (intensity, training load, ACWR, ...)
    """

    df_master = pd.merge(df_clean, df_split_features,
                         on="activity_id", how="left")

    # --- HR INTENSITY ---
    df_master['hr_intensity'] = (
        df_master["pct_Z1"].fillna(0) * 1 +
        df_master["pct_Z2"].fillna(0) * 2 +
        df_master["pct_Z3"].fillna(0) * 3 +
        df_master["pct_Z4"].fillna(0) * 4
    )

    # --- TRAINING LOAD ---
    df_master['training_load'] = round(
        df_master['hr_intensity'] *
        ((df_master['distance_activity'] +
          df_master['elevation_gain_activity'] * 10) / 100),
        2
    )

    # --- ACUTE & CHRONIC LOADS (EWMA method) ---
    def ewma_load(x, span):
        return x.ewm(span=span, min_periods=1).mean()

    df_master['acute_load'] = df_master.groupby("athlete_id")['training_load'] \
                                       .transform(lambda x: ewma_load(x, span=7))

    df_master['chronic_load'] = df_master.groupby("athlete_id")['training_load'] \
                                         .transform(lambda x: ewma_load(x, span=28))

    df_master['acwr'] = round(df_master['acute_load'] / df_master['chronic_load'], 3)

    # --- 1) Relative distance per athlete ------------------------
    df_master['distance_relative'] = (
        df_master['distance_activity'] /
        df_master.groupby('athlete_id')['distance_activity'].transform('median')
    )

# --- 2) Relative training load per athlete -------------------
    df_master['training_load_relative'] = (
        df_master['training_load'] /
        df_master.groupby('athlete_id')['training_load'].transform('median')
    )

# --- 3) Add VDOT_max from athletes_summary -------------------
    df_master = df_master.merge(
        df_athletes_summary_new[['athlete_id', 'VDOT_max']],
        on='athlete_id',
        how='left'
    )

# --- 4) Compute VDOT speed (expected speed from physiology) --
    df_master['VDOT_speed'] = df_master['VDOT_max'].apply(vdot_to_speed)

# If VDOT is missing → use global median running speed
    global_median_speed = df_master['average_speed_km_h_activity'].median()
    df_master['VDOT_speed'] = df_master['VDOT_speed'].fillna(global_median_speed)

# --- 5) Speed relative to athlete potential ------------------
    df_master['speed_relative'] = (
        df_master['average_speed_km_h_activity'] /
        df_master['VDOT_speed']
    )

# --- 6) Clean duplicates by activity_id ----------------------
    df_master.drop_duplicates(subset=['activity_id'], inplace=True)

    return df_master



# --- MAIN EXECUTION BLOCK ---

if __name__ == "__main__":
    # --- 0. PATHS & DIRECTORIES ---
    BASE_DIR = Path(__file__).resolve().parents[1]
    DATA_PATH = BASE_DIR / "data" / "raw"
    OUTPUT_PATH = BASE_DIR / "data" / "processed"
    MANUAL_STATS_PATH = BASE_DIR / "data" / "manual_athlete_stats.csv"
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

    # --- 1. LOAD RAW DATA ---
    logging.info("Step 1: Loading raw data...")
    # print("Step 1: Loading raw data...")
    df_raw = load_data(DATA_PATH)

    # --- 2. LOAD EXISTING PROCESSED DATA (IF ANY) ---
    logging.info("Step 2: Checking for existing processed data...")
    # print("Step 2: Checking for existing processed data...")
    existing_master_path = OUTPUT_PATH / "activities_master.csv"
    if existing_master_path.exists():
        df_master_existing = pd.read_csv(existing_master_path, parse_dates=["start_date"])
        processed_ids = set(df_master_existing["activity_id"].unique())
        logging.info(f"Found {len(processed_ids)} activities already processed")
        # print(f"Found {len(processed_ids)} activities already processed")
    else:
        df_master_existing = pd.DataFrame()
        processed_ids = set()

    # --- 3. FILTER NEW ACTIVITIES ---
    df_new = df_raw[~df_raw["id"].isin(processed_ids)].copy()
    logging.info(f"Found {len(df_new)} new activities to process")
    # print(f"Found {len(df_new)} new activities to process")

    if df_new.empty:
        logging.info("No new activities detected -> Pipeline finished")
        # print("No new activities detected -> Pipeline finished")
        exit(0)

    # --- 4. CLEANING & BASIC DATA EXTRACTION ---
    logging.info("Step 3: Cleaning activities and processing best efforts...")
    # print("Step 3: Cleaning activities and processing best efforts...")
    df_clean, _ = clean_activities(df_new.copy())
    df_best_efforts, df_activity_splits = process_best_efforts(df_new.copy())

    # --- 5. GENERATE ATHLETE SUMMARY TABLE ---
    logging.info("Step 4: Generating athlete summary statistics...")
    # print("Step 4: Generating athlete summary statistics...")
    df_athletes_summary_new = generate_athlete_stats(df_clean, df_best_efforts, MANUAL_STATS_PATH)

    # --- 6. CREATE/UPDATE MASTER TABLE ---
    logging.info("Step 5: Creating the 'activities_master' table for new activities...")
    # print("Step 5: Creating the 'activities_master' table for new activities...")

    # a) Create activity-level features from splits (CV speed, % HR zones)
    max_hr_dict = df_athletes_summary_new.set_index("athlete_id")["max_hr"].to_dict()
    df_split_features = process_splits(df_activity_splits, max_hr_dict)

    # b) Merge these new features with our base activity table `df_clean`
    df_master_new = build_activity_master(df_clean, df_split_features, df_athletes_summary_new)

    #df_master_new['training_load'] = round(df_master_new['hr_intensity'] * (
    #    (df_master_new['distance_activity'] + df_master_new['elevation_gain_activity'] * 10) / 100), 2)
    # --> I found this way in order to include elevation gain in the training load calculation, the x10 factor is arbitrary and can be adjusted

    # We will also use the ACWR (Acute Chronic Workload Ratio, different sources: Lolli et al., Griffin et al., Gabbett) concept to calculate a fatigue index:
    # the ratio of the last 7 days of training load to the last 28 days (21 days is also used in some studies)
    # How to interpret it? -> 
    # Below 0.8 = undertraining
    # 0.8 to 1.3 = optimal zone
    # Above 1.5 = overtraining, risk of injury increases considerably (Gabbett, 2018)

    # Use of the EWMA method to calculate the acute and chronic load -> it gives more weight to recent activities and is, therefore, more accurate -->
    # (https://www.researchgate.net/publication/311860780_Calculating_acute_Chronic_workload_ratios_using_exponentially_weighted_moving_averages_provides_a_more_sensitive_indicator_of_injury_likelihood_than_rolling_averages#:~:text=The%20variance%20(R(2)),injury%20risk%20with%20higher%20ACWR.)

    df_master_new['cv_speed'] = df_master_new['cv_speed'].fillna(0)
    df_master_new = df_master_new.drop(columns=['splits_metric', 'best_efforts', 'acute_load', 'chronic_load', 'hr_intensity'])

    # d) Compute the cumulative percentage of time spent in each zone (to change for cycling and swimming later)
    # Time in each zone (in seconds)
    df_master_new["time_Z1"] = df_master_new["pct_Z1"] * df_master_new["moving_time_activity"]
    df_master_new["time_Z2"] = df_master_new["pct_Z2"] * df_master_new["moving_time_activity"]
    df_master_new["time_Z3"] = df_master_new["pct_Z3"] * df_master_new["moving_time_activity"]
    df_master_new["time_Z4"] = df_master_new["pct_Z4"] * df_master_new["moving_time_activity"]

    # Cumulative time per athlete
    df_master_new["cumulative_time"] = df_master_new.groupby("athlete_id")["moving_time_activity"].cumsum()
    df_master_new["cumulative_Z1"] = df_master_new.groupby("athlete_id")["time_Z1"].cumsum()
    df_master_new["cumulative_Z2"] = df_master_new.groupby("athlete_id")["time_Z2"].cumsum()
    df_master_new["cumulative_Z3"] = df_master_new.groupby("athlete_id")["time_Z3"].cumsum()
    df_master_new["cumulative_Z4"] = df_master_new.groupby("athlete_id")["time_Z4"].cumsum()

    # Cumulative percentage of time spent in each zone
    df_master_new["pct_time_Z1"] = (df_master_new["cumulative_Z1"] / df_master_new["cumulative_time"] * 100).round(2)
    df_master_new["pct_time_Z2"] = (df_master_new["cumulative_Z2"] / df_master_new["cumulative_time"] * 100).round(2)
    df_master_new["pct_time_Z3"] = (df_master_new["cumulative_Z3"] / df_master_new["cumulative_time"] * 100).round(2)
    df_master_new["pct_time_Z4"] = (df_master_new["cumulative_Z4"] / df_master_new["cumulative_time"] * 100).round(2)

    # Cumulative percentage during the last 30 and 60 days
    def pct_time_last_days(df, days):
        df = df.copy()
        results = []

        for athlete_id, group in df.groupby("athlete_id"):
            group = group.sort_values("start_date").set_index("start_date")

            rolling_time = group["moving_time_activity"].rolling(f"{days}D").sum()
            rolling_Z1   = group["time_Z1"].rolling(f"{days}D").sum()
            rolling_Z2   = group["time_Z2"].rolling(f"{days}D").sum()
            rolling_Z3   = group["time_Z3"].rolling(f"{days}D").sum()
            rolling_Z4   = group["time_Z4"].rolling(f"{days}D").sum()

            pct_Z1 = (rolling_Z1 / rolling_time * 100).fillna(0).round(2)
            pct_Z2 = (rolling_Z2 / rolling_time * 100).fillna(0).round(2)
            pct_Z3 = (rolling_Z3 / rolling_time * 100).fillna(0).round(2)
            pct_Z4 = (rolling_Z4 / rolling_time * 100).fillna(0).round(2)

            tmp = pd.DataFrame({
                "athlete_id": athlete_id,
                f"pct_time_Z1_last_{days}d": pct_Z1,
                f"pct_time_Z2_last_{days}d": pct_Z2,
                f"pct_time_Z3_last_{days}d": pct_Z3,
                f"pct_time_Z4_last_{days}d": pct_Z4,
            }, index=group.index)

            results.append(tmp)

        return pd.concat(results)

    pct_30d = pct_time_last_days(df_master_new, 30).drop(columns=["athlete_id"])
    pct_60d = pct_time_last_days(df_master_new, 60).drop(columns=["athlete_id"])

    df_master_new = df_master_new.join(pct_30d, on="start_date")
    df_master_new = df_master_new.join(pct_60d, on="start_date")

    df_master_new = df_master_new.drop(columns=["time_Z1", "time_Z2", "time_Z3", "time_Z4", "cumulative_time", "cumulative_Z1", "cumulative_Z2", "cumulative_Z3", "cumulative_Z4"])

    # e) Compute the cumulative training load for the last 2, 4 and 8 weeks
    def cumulative_load_last_weeks(df):
        df["start_date"] = pd.to_datetime(df["start_date"])
        df = df.sort_values(by=["athlete_id", "start_date"])
        df = df.set_index("start_date")
        df['cumulative_training_load_2_weeks'] = (df.groupby('athlete_id')['training_load'].rolling('14D', min_periods=1).sum().reset_index(level=0, drop=True))
        df['cumulative_training_load_4_weeks'] = (df.groupby('athlete_id')['training_load'].rolling('28D', min_periods=1).sum().reset_index(level=0, drop=True))
        df['cumulative_training_load_8_weeks'] = (df.groupby('athlete_id')['training_load'].rolling('56D', min_periods=1).sum().reset_index(level=0, drop=True))
        df = df.reset_index()

        return df

    df_master_new = cumulative_load_last_weeks(df_master_new)


    # --- 7. ADD WEATHER DATA ---
    logging.info("Step 6: Fetching weather data for new activities...")
    # print("Step 6: Fetching weather data for new activities...")
    df_master_new['start_date'] = pd.to_datetime(df_master_new['start_date'])
    weather_data = df_master_new.apply(get_weather_for_activity, axis=1)
    df_master_new = pd.concat([df_master_new, weather_data], axis=1)
    df_master = df_master_new.drop(columns=['start_latlng'])

    # --- 8. MERGE NEW WITH EXISTING DATA ---
    df_master_final = pd.concat([df_master_existing, df_master_new], ignore_index=True)

    # --- 9. SAVE UPDATED DATA ---
    logging.info("Step 7: Saving updated datasets...")
    # print("Step 7: Saving updated datasets...")
    df_master_final.to_csv(OUTPUT_PATH / "activities_master.csv", index=False)

    # Append / update the other tables too
    df_best_efforts.to_csv(OUTPUT_PATH / "best_efforts.csv", mode="a", header=not (OUTPUT_PATH / "best_efforts.csv").exists(), index=False)
    df_activity_splits.to_csv(OUTPUT_PATH / "activity_splits.csv", mode="a", header=not (OUTPUT_PATH / "activity_splits.csv").exists(), index=False)
    df_athletes_summary_new.to_csv(OUTPUT_PATH / "athletes_summary.csv", mode="a", header=not (OUTPUT_PATH / "athletes_summary.csv").exists(), index=False)

    # Optionally push to SQL
    # df_master_new.to_sql("activities_master", engine, if_exists="append", index=False)

    logging.info("Pipeline completed successfully!")
    # print("Pipeline completed successfully!")
    logging.info(f"Files saved in: {OUTPUT_PATH}")
    # print(f"Files saved in: {OUTPUT_PATH}")