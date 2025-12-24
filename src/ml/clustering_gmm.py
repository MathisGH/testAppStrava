import pandas as pd
import numpy as np
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler
from pathlib import Path
import logging
import joblib

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

FEATURE_COLUMNS = [
    "cv_speed",
    "pct_Z1", "pct_Z2", "pct_Z3", "pct_Z4",
    "speed_relative",
    "distance_relative"
]

def load_or_train_gmm(X, n_components=4, model_path="models"):
    model_path = Path(model_path)
    gmm_file = model_path / "gmm.pkl"
    scaler_file = model_path / "scaler.pkl"

    if gmm_file.exists() and scaler_file.exists():
        logging.info("Loading existing scaler + GMM model...")
        scaler = joblib.load(scaler_file)
        gmm = joblib.load(gmm_file)
        return scaler, gmm

    logging.info("Training new scaler + GMM...")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    gmm = GaussianMixture(n_components=n_components, covariance_type="full", random_state=15, n_init=10)
    gmm.fit(X_scaled)

    model_path.mkdir(parents=True, exist_ok=True)
    joblib.dump(scaler, scaler_file)
    joblib.dump(gmm, gmm_file)

    logging.info("Saved scaler + GMM in models/")
    return scaler, gmm


def prepare_X(df):
    X = df[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan)
    X_filled = X.fillna(0)

    valid_mask = (
        df["pct_Z1"] +
        df["pct_Z2"] +
        df["pct_Z3"] +
        df["pct_Z4"]
    ) > 0

    df_valid = df.loc[valid_mask].copy()
    X_valid = X.loc[valid_mask].fillna(0)

    return df_valid, X_valid, valid_mask

def run_clustering(
    input_path="data/processed/activities_master.csv",
    output_path="data/processed/activities_master_with_gmm.csv",
    model_path="models",
    n_components=4
):
    logging.info("Loading activities_master...")
    df = pd.read_csv(input_path)

    # Only RUN
    df_run = df[df["sport_type"] == "Run"].copy()

    # Prepare features
    df_run_clean, X_clean, valid_mask = prepare_X(df_run)

    # Load or train GMM
    scaler, gmm = load_or_train_gmm(X_clean, n_components=n_components, model_path=model_path)
    X_scaled = scaler.transform(X_clean)

    probas = gmm.predict_proba(X_scaled)

    cluster_main = np.argmax(probas, axis=1)
    cluster_confidence_main = np.max(probas, axis=1)
    cluster_second = np.argsort(probas, axis=1)[:, -2]
    cluster_confidence_second = np.sort(probas, axis=1)[:, -2]

    df_run_clean["cluster"] = cluster_main
    df_run_clean["cluster_confidence"] = cluster_confidence_main
    df_run_clean["cluster_second"] = cluster_second
    df_run_clean["cluster_confidence_second"] = cluster_confidence_second

    df_run = df_run.merge(
        df_run_clean[["activity_id", "cluster", "cluster_confidence", "cluster_second", "cluster_confidence_second"]],
        on="activity_id",
        how="left"
    )

    df_run["cluster"] = df_run["cluster"].fillna(-1).astype(int)
    df_run["cluster_confidence"] = df_run["cluster_confidence"].fillna(0)
    df_run["cluster_second"] = df_run["cluster_second"].fillna(-1).astype(int)
    df_run["cluster_confidence_second"] = df_run["cluster_confidence_second"].fillna(0)

    df_full = df.merge(
        df_run[["activity_id", "cluster", "cluster_confidence", "cluster_second", "cluster_confidence_second"]],
        on="activity_id",
        how="left"
    )

    df_full["cluster"] = df_full["cluster"].fillna(-1).astype(int)
    df_full["cluster_confidence"] = df_full["cluster_confidence"].fillna(0)
    df_full["cluster_second"] = df_full["cluster_second"].fillna(-1).astype(int)
    df_full["cluster_confidence_second"] = df_full["cluster_confidence_second"].fillna(0)
    df_full = df_full.drop_duplicates(subset=['activity_id'])

    logging.info(f"Saving output to {output_path}...")
    df_full.to_csv(output_path, index=False)
    logging.info("Clustering complete.")

if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parents[2]

    INPUT = BASE_DIR / "data" / "processed" / "activities_master.csv"
    OUTPUT = BASE_DIR / "data" / "processed" / "activities_master_with_gmm.csv"
    MODELS = BASE_DIR / "models"

    run_clustering(
        input_path=INPUT,
        output_path=OUTPUT,
        model_path=MODELS,
        n_components=3
    )

    logging.info("GMM clustering completed successfully.")
