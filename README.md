# Athlete Performance Analysis

Analyzes Strava activity data to help athletes improve performance and predict results.

Powered by Strava – Data sourced via the Strava API. Each activity links back to Strava:
View on Strava: https://www.strava.com/activities/{activity_id}

⚠ Not affiliated with Strava.


## Overview
- 'server.py': Flask app for Strava authentification and token storage
- 'fetch_activities.py': Dowloads all Strava activities for every athlete in athletes.json
- 'csv_to_json.py': Converts the CSV file from Google Sheet to a JSON file
- 'notebook_strava.ipynb': Notebook for EDA
- More coming soon...

## Training analysis
- Data engineering: creating new variables like activity intensity and training load
- Clustering: group training sessions based on heart rate zones, speed variability, and intensity
- Training load estimation: analyze effort levels to identify risks of overtraining or injury
- Performance prediction: use machine learning (e.g., Random Forest) to estimate personal bests
- More coming soon...



# Files (.csv) used in the repository

## Data
- **athletes_token**: contains athletes’ authentication tokens  
  Columns: `id`, `firstname`, `lastname`, `access_token`, `refresh_token`

- **manual_stats**: contains manually entered stats for each athlete  
  Columns: `athlete_id`, `total_distance_run`, `total_distance_ride`, `total_distance_swim`, `FC_max`, `PB_5k`, `PB_10k`, `PB_21k`, `PB_42k`, `Nb_activities_run`, `Nb_activities_ride`, `Nb_activities_swim`, `Nb_activities_workout`

---

## Processed (4 main files)

- **athletes_summary**: contains aggregated statistics for each athlete  
  Columns: `athlete_id`, `Nb_activities_run`, `Nb_activities_ride`, `Nb_activities_swim`, `Nb_activities_workout`, `Total_distance_run`, `Total_distance_ride`, `Total_distance_swim`, `FC_max`, `PB_5km`, `PB_10km`, `PB_21.1km`, `PB_42.2km`, `Nb_activities`, `VDOT_5km`, `VDOT_10km`, `VDOT_21.1km`, `VDOT_42.2km`, `VDOT_max`

- **best_efforts**: contains the personal bests (PBs) of each athlete for different distances  
  Columns: `distance_activity`, `moving_time_activity`, `elevation_gain_activity`, `sport_type`, `activity_id`, `athlete_id`, `id`, `best_effort_name`, `moving_time`, `start_date`, `distance_best_effort`, `pr_rank`

- **activity_splits**: contains every split of every activity for every athlete  
  Columns: `distance_activity`, `moving_time_activity`, `elevation_gain_activity`, `sport_type`, `activity_id`, `start_date`, `average_watts_activity`, `average_heartrate_activity`, `max_heartrate_activity`, `athlete_id`, `max_watts_activity`, `weighted_average_watts_activity`, `average_speed_km_h_activity`, `max_speed_km_h_activity`, `cumulative_distance_run`, `cumulative_distance_ride`, `cumulative_distance_swim`, `distance_split`, `moving_time_split`, `average_speed_split`, `average_heartrate_split`, `average_speed_km_h_split`

- **activities_master**: contains every activity of every athlete, with added features used for analysis  
  Columns: `distance_activity`, `moving_time_activity`, `elevation_gain_activity`, `sport_type`, `activity_id`, `start_date`, `average_watts_activity`, `average_heartrate_activity`, `max_heartrate_activity`, `athlete_id`, `max_watts_activity`, `weighted_average_watts_activity`, `average_speed_km_h_activity`, `max_speed_km_h_activity`, `cumulative_distance_run`, `cumulative_distance_ride`, `cumulative_distance_swim`, `cv_speed`, `pct_Z1`, `pct_Z2`, `pct_Z3`, `pct_Z4`, `intensity`, `training_load`

---

## Raw
- **activities_<athlete_id>_<firstname>_<lastname>**: contains all raw data of every activity for each athlete
