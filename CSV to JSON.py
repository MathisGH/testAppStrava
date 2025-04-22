import pandas as pd
import json

### Pour transformer le gsheet (.csv) en json
# Charger le fichier CSV
df = pd.read_csv("Athletes Strava.csv")

athletes = {}
for _, row in df.iterrows():
    athlete_id = str(row["id"])
    athletes[athlete_id] = {
        "firstname": row["firstname"],
        "lastname": row["lastname"],
        "access_token": row["access_token"],
        "refresh_token": row["refresh_token"]
    }

# Sauvegarder dans un fichier JSON
with open("athletes.json", "w") as f:
    json.dump({"athletes": athletes}, f, indent=4)

print("Conversion terminée : athletes.json créé")
