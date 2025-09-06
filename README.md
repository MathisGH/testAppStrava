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