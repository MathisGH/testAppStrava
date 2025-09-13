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



# Files (.csv) we are using in each repository:
- data
-> athletes_token : id, firstname, lastname, access_token, refresh_token
-> manual_stats : athlete_id, total_distance_run/ride/swim, FC max, 5k/10k/21k/42k PBs, Nb_activities_run/ride/swim/workout

--- processed
---> df_activites_agg : athlete_id, activity_id, start_date, cv_speed, pct_Z1, pct_Z2, pct_Z3, pct_Z4, sport_type, distance, moving_time, intensity, training_load

---> df_athletes_stats : athlete_id, total_distance_run/ride/swim, FC max, 5k/10k/21k/42k PBs and VDOT and VDOT_max, Nb_activities_run/ride/swim/workout/total

---> df_best_efforts : distance_activity, moving_time_activity, sport_type, activity_id, athlete_id, id, best_effort_name, moving_time, start_date, distance_best_effort, pr_rank

---> df_clean : distance_activity, moving_time_activity, elevation_gain_activity, sport_type, activity_id, start_date, average_watts_activity, average_heartrate_activity,           ________________max_heartrate_activity, athlete_id, max_watts_activity, weighted_average_watts_activity, average_speed_km_h_activity, max_speed_km_h_activity, ________________cumulative_distance_run, cumulative_distance_ride, cumulative_distance_swim

---> df_clean_enriched : distance, moving_time, sport_type, activity_id, start_date, average_heartrate, athlete_id, average_speed_km_h, cv_speed, pct_Z1, pct_Z2, pct_Z3, pct_Z4

---> df_final : distance, moving_time, sport_type, activity_id, start_date, average_heartrate, athlete_id, average_speed_km_h

----- activities_by_sport
-----> stats for every activities for each sport type...

--- raw
---> activities_123456789_firstname_lastname : everything about every activity for each athlete