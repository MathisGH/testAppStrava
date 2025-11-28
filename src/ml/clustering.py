import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from pathlib import Path
import math
import logging
import os
import joblib

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

def prepare_features(activities_master, athletes_summary):
    df = activities_master.copy()

    df['distance_relative'] = df['distance_activity'] / df.groupby('athlete_id')['distance_activity'].transform('median')
    df['training_load_relative'] = df['training_load'] / df.groupby('athlete_id')['training_load'].transform('median')

    df = df.merge(athletes_summary[['athlete_id', 'VDOT_max']], on='athlete_id', how='left')
    df.drop_duplicates(subset=['activity_id'], inplace=True)

    df['VDOT_speed'] = df['VDOT_max'].apply(vdot_to_speed)
    global_median_speed = df['average_speed_km_h_activity'].median() # will change this later
    df['VDOT_speed'] = df['VDOT_speed'].fillna(global_median_speed) # will change this later

    df['speed_relative'] = df['average_speed_km_h_activity'] / df['VDOT_speed']

    # keep only runs for now
    mask = df['sport_type'] == 'Run'
    features = ['cv_speed', 'pct_Z1', 'pct_Z2', 'pct_Z3', 'pct_Z4',
                'speed_relative', 'distance_relative', 'training_load_relative']

    df_features = df[mask].copy()

    # save original index and activity_id to remerge later
    df_features = df_features.reset_index().rename(columns={'index': 'original_idx'})
    df_features = df_features[['original_idx', 'activity_id'] + features]

    X = df_features[features].replace([np.inf, -np.inf], np.nan)
    X_clean = X.dropna()
    df_features = df_features.loc[X_clean.index].reset_index(drop=True)
    X_clean = X_clean.reset_index(drop=True)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_clean)

    return df_features, X_clean, X_scaled, scaler

def train_and_save_kmeans(X_scaled, n_clusters=5, model_path="models"):
    logging.info(f"Training KMeans with k={n_clusters}")
    kmeans = KMeans(n_clusters=n_clusters, random_state=15, n_init=10)
    kmeans.fit(X_scaled)

    os.makedirs(model_path, exist_ok=True)
    joblib.dump(kmeans, os.path.join(model_path, "kmeans.pkl"))
    logging.info("Saved KMeans to models/kmeans.pkl")
    return kmeans

def assign_clusters_and_merge(activities_master, df_features, X_scaled, kmeans, scaler, model_path="models"):
    labels = kmeans.predict(X_scaled)

    df_clusters = df_features[['original_idx', 'activity_id']].copy().reset_index(drop=True)
    df_clusters['cluster'] = labels

    master = activities_master.copy().reset_index().rename(columns={'index': 'original_idx'})

    master = master.merge(df_clusters[['original_idx', 'cluster']], on='original_idx', how='left')
    master['cluster'] = master['cluster'].fillna(-1).astype(int) # unclustered activities get cluster -1 (just in case)

    out_dir = Path("data/processed")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "activities_master_with_clusters.csv"
    master.to_csv(out_csv, index=False)
    logging.info(f"Saved master with clusters to {out_csv}")

    os.makedirs(model_path, exist_ok=True)
    joblib.dump(scaler, os.path.join(model_path, "scaler.pkl"))
    joblib.dump(kmeans, os.path.join(model_path, "kmeans.pkl"))
    logging.info(f"Saved scaler and kmeans in {model_path}")

    return master

if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parents[1].parent
    ACTIVITIES_PATH = BASE_DIR / "data" / "processed" / "activities_master.csv"
    ATHLETES_PATH = BASE_DIR / "data" / "processed" / "athletes_summary.csv"

    activities_master = pd.read_csv(ACTIVITIES_PATH)
    athletes_summary = pd.read_csv(ATHLETES_PATH)

    df_features, X_clean, X_scaled, scaler = prepare_features(activities_master, athletes_summary)

    if X_scaled.shape[0] == 0:
        logging.error("No rows available after cleaning/imputation")
        raise SystemExit(1)

    kmeans = train_and_save_kmeans(X_scaled, n_clusters=5)
    master_with_clusters = assign_clusters_and_merge(activities_master, df_features, X_scaled, kmeans, scaler)

    logging.info("Clustering done")
