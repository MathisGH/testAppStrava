import pandas as pd
import numpy as np
import os
import ast
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)


def load_data(filepath: Path) -> pd.DataFrame:
    """Load all CSV files from the given directory into a single DataFrame"""
    df = pd.concat(
        [pd.read_csv(os.path.join(filepath, f)) for f in os.listdir(filepath) if f.endswith(".csv")],
        ignore_index=True
    )
    return df


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
    df['athlete'] = df['athlete'].apply(ast.literal_eval)
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
            df.groupby('athlete_id', group_keys=False)
            .apply(lambda x: x.loc[x['sport_type'] == sport, 'distance_activity'].cumsum())
        )

    df['cumulative_distance_run'] = cumulative_distance(df, 'Run')
    df['cumulative_distance_ride'] = cumulative_distance(df, 'Ride')
    df['cumulative_distance_swim'] = cumulative_distance(df, 'Swim')

    # Explode and flatten splits
    df['splits_metric'] = df['splits_metric'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
    df_splits_metric = df.explode("splits_metric").reset_index(drop=True)
    df_splits_metric = pd.concat(
        [df_splits_metric.drop(columns=["splits_metric"]), df_splits_metric["splits_metric"].apply(pd.Series)],
        axis=1
    )
    df = df.drop(columns=["splits_metric"])

    return df, df_splits_metric


def process_best_efforts(df: pd.DataFrame, df_splits_metric: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Extract and process best effort data and integrate with cleaned splits
       Returns df_best_efforts and df_final (fusion splits/no_splits)"""
    df['best_efforts'] = df['best_efforts'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
    df_efforts = df[df['best_efforts'].apply(lambda x: isinstance(x, list) and len(x) > 0)].copy()
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
        'elapsed_time', 'elevation_difference', 0, 'average_grade_adjusted_speed',
        'cumulative_distance_swim', 'cumulative_distance_ride', 'cumulative_distance_run',
        'pace_zone', 'split'
    ], errors='ignore')

    for col in ['splits_metric', 'best_efforts']:
        for d in [df, df_splits_metric, df_best_efforts]:
            if col in d.columns:
                d.drop(columns=[col], inplace=True)

    df_best_efforts = df_best_efforts.dropna(subset=['pr_rank'])
    keep_cols_best_efforts = [
        'distance_activity', 'moving_time_activity', 'sport_type',
        'activity_id', 'athlete_id', 'id', 'best_effort_name', 'moving_time',
        'start_date', 'distance_best_effort', 'pr_rank'
    ]
    df_best_efforts = df_best_efforts[keep_cols_best_efforts]
    df_best_efforts['start_date'] = pd.to_datetime(df_best_efforts['start_date'])
    df_best_efforts['moving_time'] = df_best_efforts['moving_time'] / 60
    df_best_efforts = df_best_efforts[~df_best_efforts['best_effort_name'].isin(
        ['2 mile', '1/2 mile', '10 mile', '1K', '400m', '15K', '1 mile']
    )]

    # Fusion no_splits / only_splits
    df_activity_no_splits = df_splits_metric[df_splits_metric['distance_split'].isnull()].copy()
    df_activity_only_splits = df_splits_metric[df_splits_metric['distance_split'].notnull()].copy()

    df_activity_only_splits = df_activity_only_splits.drop(
        columns=[col for col in df_activity_only_splits.columns if 'activity' in col and col != 'activity_id'],
        errors='ignore'
    )
    df_activity_no_splits = df_activity_no_splits.drop(
        columns=[col for col in df_activity_no_splits.columns if 'split' in col],
        errors='ignore'
    )

    df_activity_only_splits = df_activity_only_splits.rename(columns={
        'distance_split': 'distance',
        'moving_time_split': 'moving_time',
        'average_speed_km_h_split': 'average_speed_km_h',
        'average_heartrate_split': 'average_heartrate'
    }).drop(columns=['average_speed_split'], errors='ignore')

    df_activity_no_splits = df_activity_no_splits.rename(columns={
        'distance_activity': 'distance',
        'moving_time_activity': 'moving_time',
        'average_speed_km_h_activity': 'average_speed_km_h',
        'average_heartrate_activity': 'average_heartrate'
    }).drop(columns=[col for col in df_activity_no_splits.columns if col not in df_activity_only_splits.columns], errors='ignore')

    df_final = pd.concat([df_activity_no_splits, df_activity_only_splits], ignore_index=True)
    df_final.dropna(subset=['average_heartrate'], inplace=True)

    return df_best_efforts, df_final


def save_outputs(df_clean: pd.DataFrame, df_best: pd.DataFrame, df_final: pd.DataFrame, output_dir: Path):
    """Save cleaned data to CSV files"""
    output_dir.mkdir(parents=True, exist_ok=True)
    df_clean.to_csv(output_dir / "df_clean.csv", index=False)
    df_best.to_csv(output_dir / "df_best_efforts.csv", index=False)
    df_final.to_csv(output_dir / "df_final.csv", index=False)


if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parents[1]
    DATA_PATH = BASE_DIR / "data" / "raw"
    OUTPUT_PATH = BASE_DIR / "data" / "processed"

    df_raw = load_data(DATA_PATH)
    df_clean, df_splits_metric = clean_activities(df_raw)
    df_best_efforts, df_final = process_best_efforts(df_clean, df_splits_metric)
    save_outputs(df_clean, df_best_efforts, df_final, OUTPUT_PATH)

