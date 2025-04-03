import requests
import pandas as pd
import os
import json
import time

ATHLETES_FILE = "athletes.json"
DATA_FOLDER = "Data"
AUTH_URL = "https://www.strava.com/oauth/token"
ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
ACTIVITY_DETAILS_URL = "https://www.strava.com/api/v3/activities/"

os.makedirs(DATA_FOLDER, exist_ok=True)  # Créer le dossier si inexistant

def load_athletes():
    with open(ATHLETES_FILE, "r") as f:
        return json.load(f)["athletes"]

def save_athletes(data):
    with open(ATHLETES_FILE, "w") as f:
        json.dump({"athletes": data}, f, indent=4)

def refresh_token(athlete):
    """ Rafraîchit le token d'accès """
    payload = {
        "client_id": "152701",
        "client_secret": "f9994d3d0eac0d314a1ee9c94ccb2dd674debb5d",
        "refresh_token": athlete["refresh_token"],
        "grant_type": "refresh_token"
    }
    res = requests.post(AUTH_URL, data=payload).json()
    athlete["access_token"] = res.get("access_token", athlete["access_token"])
    athlete["refresh_token"] = res.get("refresh_token", athlete["refresh_token"])
    return athlete

def fetch_activities():
    """ Récupère les nouvelles activités avec détails pour chaque athlète """
    athletes = load_athletes()
    
    for athlete_id, athlete in athletes.items():
        print(f"📊 Récupération des activités pour {athlete['firstname']} {athlete['lastname']}")
        
        # Rafraîchir le token et sauvegarder
        athlete = refresh_token(athlete)
        save_athletes(athletes)

        headers = {'Authorization': f'Bearer {athlete["access_token"]}'}
        file_path = os.path.join(DATA_FOLDER, f"activities_{athlete_id}_{athlete['firstname']}_{athlete['lastname']}.csv")
        
        # Charger les anciennes activités
        if os.path.exists(file_path):
            df_existing = pd.read_csv(file_path)
            existing_ids = set(df_existing['id'].astype(str))
        else:
            df_existing = pd.DataFrame()
            existing_ids = set()

        # Récupération des nouvelles activités
        request_page_num = 1
        new_activities = []

        while True:
            params = {'per_page': 200, 'page': request_page_num}
            response = requests.get(ACTIVITIES_URL, headers=headers, params=params).json()

            if not response:
                break

            new_data = [activity for activity in response if str(activity['id']) not in existing_ids]
            if not new_data:
                break

            new_activities.extend(new_data)
            request_page_num += 1
            print(f"📥 Page {request_page_num} récupérée ({len(new_data)} nouvelles activités)")

            # Pause pour éviter le quota API (max 100 req/15 min)
            if request_page_num % 100 == 0:
                print("🚦 Pause de 15 minutes pour éviter le quota API...")
                time.sleep(900)

        # Récupérer les détails des nouvelles activités
        detailed_activities = []
        for activity in new_activities:
            activity_id = activity['id']
            details = requests.get(f"{ACTIVITY_DETAILS_URL}{activity_id}", headers=headers).json()
            activity.update(details)
            detailed_activities.append(activity)
            print(f"📊 Détails récupérés pour l'activité {activity_id}")
            time.sleep(1)  # Pause pour respecter les quotas

        # Mise à jour du CSV
        if detailed_activities:
            df_new = pd.DataFrame(detailed_activities)
            df_final = pd.concat([df_existing, df_new], ignore_index=True)
            df_final.to_csv(file_path, index=False)
            print(f"✅ {len(detailed_activities)} nouvelles activités enregistrées pour {athlete['firstname']}")

if __name__ == "__main__":
    fetch_activities()