import pandas as pd
import numpy as np
import math
import os
from pathlib import Path
from dotenv import load_dotenv # type: ignore
load_dotenv()  # Charger les variables d'environnement depuis le fichier .env
from sqlalchemy import create_engine

password_sql = os.getenv("POSTGRES_PASSWORD")

engine = create_engine(f"postgresql://postgres:{password_sql}@localhost:5432/strava_db")

def extract_best_effort_time(df_best_efforts, distance_km):
    return (
        df_best_efforts[
            df_best_efforts['distance_best_effort'].between((distance_km - 0.2)*1000, (distance_km + 0.2)*1000)
        ].groupby('athlete_id')['moving_time'].min().round(2)
    )

def calculate_vdot(distance_m, time_sec):
    """Estimate VDOT score based on distance and time"""
    time_min = time_sec / 60
    if time_min == 0:
        return None

    velocity = distance_m / time_min  # m/min
    vo2 = -4.6 + 0.182258 * velocity + 0.000104 * velocity**2
    percent_max = 0.8 + 0.1894393 * math.exp(-0.012778 * time_min) + 0.2989558 * math.exp(-0.1932605 * time_min)
    return round(vo2 / percent_max, 2)

def process_splits(splits_df, fc_max_dict):
    """Analyze split-level HR and speed variability"""
    splits_df = splits_df.copy()

    def get_hr_zone(hr, fc_max):
        if pd.isna(hr) or pd.isna(fc_max):
            return None
        ratio = hr / fc_max
        if ratio < 0.82:
            return "Z1"
        elif ratio < 0.92:
            return "Z2"
        elif ratio < 0.97:
            return "Z3"
        else:
            return "Z4"

    splits_df["fc_max"] = splits_df["athlete_id"].map(fc_max_dict)
    splits_df["hr_zone"] = splits_df.apply(lambda row: get_hr_zone(row["average_heartrate"], row["fc_max"]), axis=1)

    results = []
    for activity_id, group in splits_df.groupby("activity_id"):
        cv_speed = group["average_speed_km_h"].std() / group["average_speed_km_h"].mean()
        zone_pct = group["hr_zone"].value_counts(normalize=True).reindex(["Z1", "Z2", "Z3", "Z4"], fill_value=0)
        zone_pct.index = [f"pct_{z}" for z in zone_pct.index]
        res = {"activity_id": activity_id, "cv_speed": cv_speed}
        res.update(zone_pct.to_dict())
        results.append(res)

    return pd.DataFrame(results)

def generate_athlete_stats(df_clean, df_best_efforts, manual_stats_path):
    """Compute athlete-level stats using df_clean (for FC max, totals) and df_best_efforts"""
    df_athletes_stats = pd.DataFrame(columns=[
        'athlete_id', 'Total_distance_run', 'Total_distance_ride', 'Total_distance_swim',
        'FC Max', '5km PB', '10km PB', '21km PB', '42km PB',
        'Nb_activities', 'Nb_activities_run', 'Nb_activities_ride', 'Nb_activities_swim', 'Nb_activities_workout'])

    for sport in ['Run', 'Ride', 'Swim', 'Workout']:
        df_athletes_stats[f'Nb_activities_{sport.lower()}'] = (
            df_clean[df_clean['sport_type'] == sport].groupby('athlete_id')['activity_id'].nunique()
        )

    df_athletes_stats['athlete_id'] = df_clean['athlete_id'].unique()

    distances = {
        'Total_distance_run': df_clean[df_clean['sport_type'] == 'Run'].groupby('athlete_id')['distance_activity'].sum(),
        'Total_distance_ride': df_clean[df_clean['sport_type'] == 'Ride'].groupby('athlete_id')['distance_activity'].sum(),
        'Total_distance_swim': df_clean[df_clean['sport_type'] == 'Swim'].groupby('athlete_id')['distance_activity'].sum()
    }
    for k, v in distances.items():
        df_athletes_stats[k] = df_athletes_stats['athlete_id'].map(v)

    # FC Max à partir de df_clean
    fc_valid = df_clean[df_clean['max_heartrate_activity'] < 210]
    fc_max = fc_valid.groupby('athlete_id')['max_heartrate_activity'].apply(lambda x: x.nlargest(10).mean())
    df_athletes_stats['FC Max'] = df_athletes_stats['athlete_id'].map(fc_max)

    # Best efforts
    for dist_km in [5, 10, 21.1, 42.2]:
        col = f"{int(dist_km)}km PB"
        df_athletes_stats[col] = df_athletes_stats['athlete_id'].map(extract_best_effort_time(df_best_efforts, dist_km))

    # Merge manual stats
    if Path(manual_stats_path).exists():
        manual_stats = pd.read_csv(manual_stats_path)
        common_cols = [c for c in df_athletes_stats.columns if c in manual_stats.columns]
        df_athletes_stats = pd.concat([df_athletes_stats, manual_stats[common_cols]], ignore_index=True)
        df_athletes_stats.drop_duplicates(subset='athlete_id', keep='last', inplace=True)

    df_athletes_stats.fillna(0, inplace=True)
    df_athletes_stats['Nb_activities'] = df_athletes_stats[[
        'Nb_activities_run', 'Nb_activities_ride', 'Nb_activities_swim', 'Nb_activities_workout'
    ]].sum(axis=1)

    # VDOT estimation
    for dist_m, label in [(5000, '5km PB'), (10000, '10km PB'), (21100, '21km PB'), (42200, '42km PB')]:
        vdot_col = f'VDOT_{label.split()[0]}'
        df_athletes_stats[vdot_col] = df_athletes_stats.apply(
            lambda row: calculate_vdot(dist_m, row[label]*60) if pd.notna(row[label]) else None, axis=1)

    df_athletes_stats['VDOT_max'] = df_athletes_stats[[
        'VDOT_5km', 'VDOT_10km', 'VDOT_21km', 'VDOT_42km'
    ]].max(axis=1)

    return df_athletes_stats

def enrich_activities_with_training_load(df_final, df_athletes_stats):
    """Use df_final for per-activity enrichment"""
    fc_max_dict = df_athletes_stats.set_index("athlete_id")["FC Max"].to_dict()
    df_processed_splits = process_splits(df_final, fc_max_dict)
    df_final = df_final.merge(df_processed_splits, on="activity_id", how="left")
    df_final['cv_speed'].fillna(0, inplace=True)

    df_agg = df_final[['athlete_id', 'activity_id', 'start_date', 'cv_speed',
                       'pct_Z1', 'pct_Z2', 'pct_Z3', 'pct_Z4', 'sport_type']].copy()
    df_agg['distance'] = df_final.groupby('activity_id')['distance'].transform('sum')
    df_agg['moving_time'] = df_final.groupby('activity_id')['moving_time'].transform('sum')
    df_agg = df_agg.drop_duplicates(subset='activity_id')

    df_agg['intensity'] = (df_agg["pct_Z1"] * 1 +
                           df_agg["pct_Z2"] * 1.5 +
                           df_agg["pct_Z3"] * 2.25 +
                           df_agg["pct_Z4"] * 3)
    df_agg['training_load'] = df_agg['intensity'] * df_agg['distance']

    dfs_by_sport = {
        sport: df.drop(columns=['sport_type']) for sport, df in df_agg.groupby('sport_type')
    }
    return df_final, df_agg, dfs_by_sport


if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR / "data" / "processed"

    # === 1. Load input data ===
    df_final = pd.read_csv(DATA_DIR / "df_final.csv", parse_dates=["start_date"])
    df_clean = pd.read_csv(DATA_DIR / "df_clean.csv", parse_dates=["start_date"]) 
    df_best_efforts = pd.read_csv(DATA_DIR / "df_best_efforts.csv")
    manual_stats_path = DATA_DIR / "manual_athlete_stats.csv"

    # === 2. Generate athlete-level stats (avec df_clean) ===
    df_athletes_stats = generate_athlete_stats(df_clean, df_best_efforts, manual_stats_path)

    # === 3. Enrich activity data (avec df_final) ===
    df_clean_enriched, df_agg, dfs_by_sport = enrich_activities_with_training_load(df_final, df_athletes_stats)

    # === 4. Save results ===
    df_athletes_stats.to_csv(DATA_DIR / "df_athletes_stats.csv", index=False)
    df_clean_enriched.to_csv(DATA_DIR / "df_clean_enriched.csv", index=False)
    df_agg.to_csv(DATA_DIR / "df_activities_agg.csv", index=False)

    for sport, df_sport in dfs_by_sport.items():
        df_sport.to_csv(DATA_DIR / 'activities_by_sport' / f"df_activities_{sport.lower()}.csv", index=False)
    
    df_clean_enriched.to_sql("activities_enriched", engine, if_exists="replace", index=False)

    print("Feature extraction complete")
