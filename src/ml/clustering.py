import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from pathlib import Path
import logging
import os
import joblib

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# FEATURE SELECTION
FEATURE_COLUMNS = [
    "cv_speed",
    "pct_Z1", "pct_Z2", "pct_Z3", "pct_Z4",
    "speed_relative",
    "distance_relative"
]

# LOAD OR TRAIN MODEL
def load_or_train_kmeans(X_scaled, n_clusters=5, model_path="models"):

    model_path = Path(model_path)
    kmeans_file = model_path / "kmeans.pkl"
    scaler_file = model_path / "scaler.pkl"

    # If both model + scaler exist → load them
    if kmeans_file.exists() and scaler_file.exists():
        logging.info("Loading existing scaler + KMeans model...")
        scaler = joblib.load(scaler_file)
        kmeans = joblib.load(kmeans_file)
        return scaler, kmeans

    # Otherwise → train new
    logging.info("Training new scaler + KMeans...")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_scaled)

    kmeans = KMeans(n_clusters=n_clusters, random_state=15, n_init=10)
    kmeans.fit(X_scaled)

    # Save
    model_path.mkdir(parents=True, exist_ok=True)
    joblib.dump(scaler, scaler_file)
    joblib.dump(kmeans, kmeans_file)

    logging.info("Saved scaler + KMeans in models/")
    return scaler, kmeans


# PREPARE X FOR CLUSTERING
def prepare_X(df):
    X = df[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan)
    X_filled = X.fillna(0)
    
    # Condition: at least one HR zone > 0
    valid_mask = (
        df["pct_Z1"] +
        df["pct_Z2"] +
        df["pct_Z3"] +
        df["pct_Z4"]
    ) > 0

    # Keep only valid activities
    df_valid = df.loc[valid_mask].copy()
    X_valid = X.loc[valid_mask].fillna(0)

    return df_valid, X_valid, valid_mask


# MAIN CLUSTERING PIPELINE
def run_clustering(input_path="data/processed/activities_master.csv",
                   output_path="data/processed/activities_master_with_clusters.csv",
                   model_path="models",
                   n_clusters=4):

    logging.info("Loading activities_master...")
    df = pd.read_csv(input_path)

    # Only RUN
    df_run = df[df["sport_type"] == "Run"].copy()

    # Prepare features
    df_run_clean, X_clean, valid_mask = prepare_X(df_run)

    # Load or train the model
    scaler, kmeans = load_or_train_kmeans(X_clean, n_clusters=n_clusters, model_path=model_path)

    # Scale and predict
    X_scaled = scaler.transform(X_clean)
    labels = kmeans.predict(X_scaled)

    # Attach clusters to df_run_clean
    df_run_clean["cluster"] = labels

    df_run = df_run.merge(
    df_run_clean[["activity_id", "cluster"]],
    on="activity_id",
    how="left"
    )

    df_run["cluster"] = df_run["cluster"].fillna(-1).astype(int)

    # Merge back into the full df (activities that are not RUN get -1)
    df_full = df.copy()

    df_full = df_full.merge(
        df_run[["activity_id", "cluster"]],
        on="activity_id",
        how="left"
    )

    df_full["cluster"] = df_full["cluster"].fillna(-1).astype(int)
    df_full = df_full.drop_duplicates(subset=['activity_id'])

    # Save output
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    print("WRITING FILE TO:", Path(output_path).resolve())
    print("Unique clusters:", np.unique(df_full["cluster"]))

    df_full.to_csv(output_path, index=False)

    logging.info(f"Saved final clustered master → {output_path}")
    return df_full


if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parents[2]
    print(BASE_DIR)
    INPUT = BASE_DIR / "data" / "processed" / "activities_master.csv"
    OUTPUT = BASE_DIR / "data" / "processed" / "activities_master_with_clusters.csv"
    MODELS = BASE_DIR / "models"

    run_clustering(input_path=INPUT, output_path=OUTPUT, model_path=MODELS, n_clusters=5)

    logging.info("Clustering completed successfully.")
