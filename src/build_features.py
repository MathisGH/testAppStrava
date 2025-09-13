import pandas as pd
import numpy as np
import os
import ast
import warnings
import math
from pathlib import Path
from dotenv import load_dotenv # type: ignore
from sqlalchemy import create_engine

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
        'max_watts', 'weighted_average_watts'
    ]
    df = df[keep_cols]

    # Process athlete ID
    df['athlete'] = df['athlete'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
    df['athlete_id'] = df['athlete'].apply(lambda x: x['id'] if isinstance(x, dict) else None)
    df = df.drop(columns=['athlete'])

    df = df.rename(columns={'id': 'activity_id'})

    # Convert times and speeds
    df['moving_time'] = df['moving_time'] / 60  # minutes
    df['average_speed_km_h'] = df['average_speed'] * 3.6
    df['max_speed_km_h_activity'] = df['max_speed'] * 3.6
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
    df_best_efforts['moving_time'] = df_best_efforts['moving_time'] / 60
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

# --- FEATURE ENGINEERING FUNCTIONS ---

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
        ratio = hr / max_hr
        if ratio < 0.82: return "Z1"
        elif ratio < 0.92: return "Z2"
        elif ratio < 0.97: return "Z3"
        else: return "Z4"

    splits_df["max_hr"] = splits_df["athlete_id"].map(max_hr_dict)
    splits_df["hr_zone"] = splits_df.apply(lambda row: get_hr_zone(row["average_heartrate_split"], row["max_hr"]), axis=1)

    results = []
    for activity_id, group in splits_df.groupby("activity_id"):
        mean_speed = group["average_speed_km_h_split"].mean()
        cv_speed = (group["average_speed_km_h_split"].std() / mean_speed) if mean_speed != 0 else 0 # Ensure mean is not zero to avoid division by zero
        
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
        col_name = f"PB_{int(dist_km) if dist_km.is_integer() else dist_km}km"
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
                df_athletes_summary.drop(columns=[f'{col}_manual'], inplace=True)
                
    df_athletes_summary.fillna(0, inplace=True)
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

# --- MAIN EXECUTION BLOCK ---

if __name__ == "__main__":
    # --- 0. PATHS & DIRECTORIES ---
    BASE_DIR = Path(__file__).resolve().parents[1]
    DATA_PATH = BASE_DIR / "data" / "raw"
    OUTPUT_PATH = BASE_DIR / "data" / "processed"
    MANUAL_STATS_PATH = BASE_DIR / "data" / "manual_athlete_stats.csv"
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

    # --- 1. LOAD RAW DATA ---
    print("Step 1: Loading raw data...")
    df_raw = load_data(DATA_PATH)

    # --- 2. CLEANING & BASIC DATA EXTRACTION ---
    print("Step 2: Cleaning activities and processing best efforts...")
    df_clean, _ = clean_activities(df_raw.copy())
    df_best_efforts, df_activity_splits = process_best_efforts(df_raw.copy())

    # --- 3. GENERATE ATHLETE SUMMARY TABLE ---
    print("Step 3: Generating athlete summary statistics...")
    df_athletes_summary = generate_athlete_stats(df_clean, df_best_efforts, MANUAL_STATS_PATH)

    # --- 4. Enrichment of the activity table to create the master table ---
    print("Step 4: Creating the 'activities_master' table...")
    
    # a) Create activity-level features from splits (CV speed, % HR zones)
    max_hr_dict = df_athletes_summary.set_index("athlete_id")["max_hr"].to_dict()
    df_split_features = process_splits(df_activity_splits, max_hr_dict)

    # b) Merge these new features with our base activity table `df_clean`
    df_master = pd.merge(df_clean, df_split_features, on="activity_id", how="left")

    # c) Calculate final features directly on the master table (training load)
    df_master['intensity'] = (df_master["pct_Z1"].fillna(0) * 1 +
                                df_master["pct_Z2"].fillna(0) * 1.5 +
                                df_master["pct_Z3"].fillna(0) * 2.25 +
                                df_master["pct_Z4"].fillna(0) * 3)
    df_master['training_load'] = df_master['intensity'] * (df_master['distance_activity'] / 1000)
    df_master['cv_speed'].fillna(0, inplace=True)
    df_master.drop(columns=['splits_metric', 'best_efforts'], inplace=True)

    # --- 5. SAVE THE 4 FINAL FILES ---
    print("Step 5: Saving final files...")
    
    df_athletes_summary.to_csv(OUTPUT_PATH / "athletes_summary.csv", index=False)
    df_best_efforts.to_csv(OUTPUT_PATH / "best_efforts.csv", index=False)
    df_activity_splits.to_csv(OUTPUT_PATH / "activity_splits.csv", index=False)
    df_master.to_csv(OUTPUT_PATH / "activities_master.csv", index=False)
    
    # for GCP
    # df_master.to_sql("activities_master", engine, if_exists="replace", index=False)
    # df_athletes_summary.to_sql("athletes_summary", engine, if_exists="replace", index=False)
    # df_best_efforts.to_sql("best_efforts", engine, if_exists="replace", index=False)

    print("Feature engineering pipeline completed successfully!")
    print(f"Files saved in: {OUTPUT_PATH}")