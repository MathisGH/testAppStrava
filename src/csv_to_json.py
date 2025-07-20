import pandas as pd
import json

# Load the Google Sheet CSV (here we assume it's already downloaded as a CSV file from Google Sheets, named "Athletes Strava.csv" and in the same directory as this script)
df = pd.read_csv("Athletes Strava.csv")

# Build the dictionary of athletes
athletes = {}
for _, row in df.iterrows():
    athlete_id = str(row["id"])
    athletes[athlete_id] = {
        "firstname": row["firstname"],
        "lastname": row["lastname"],
        "access_token": row["access_token"],
        "refresh_token": row["refresh_token"]
    }

# Save the dictionary as a JSON file
with open("athletes.json", "w") as f:
    json.dump({"athletes": athletes}, f, indent=4)

print("Done: athletes.json has been created")