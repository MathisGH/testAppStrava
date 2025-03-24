import requests
import urllib3
import pandas as pd
import os
import time

# Désactiver les avertissements SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Paramètres d'authentification Strava
auth_url = "https://www.strava.com/oauth/token"
athlete_url = "https://www.strava.com/api/v3/athlete"
activities_url = "https://www.strava.com/api/v3/athlete/activities"
activity_details_url = "https://www.strava.com/api/v3/activities/"

payload = {
    'client_id': "152701",
    'client_secret': 'f9994d3d0eac0d314a1ee9c94ccb2dd674debb5d',
    'refresh_token': 'ae7a27f6dde47027f5f45ab84133371767ddc69b',
    'grant_type': 'refresh_token'
}

# Obtenir le token d'accès
print("🔄 Obtention du token d'accès...")
res = requests.post(auth_url, data=payload, verify=False)
access_token = res.json()['access_token']
print("✅ Token obtenu !")

# En-tête pour les requêtes API
header = {'Authorization': f'Bearer {access_token}'}

# Récupération des infos de l'athlète
athlete_data = requests.get(athlete_url, headers=header).json()
athlete_id = athlete_data['id']
athlete_firstname = athlete_data.get('firstname', 'unknown')
athlete_lastname = athlete_data.get('lastname', 'unknown')

# Définition du fichier CSV
data_folder = "Data"
os.makedirs(data_folder, exist_ok=True)  # Créer le dossier s'il n'existe pas
file_path = os.path.join(data_folder, f"activities_{athlete_id}_{athlete_firstname}_{athlete_lastname}.csv")

# Charger les activités existantes
if os.path.exists(file_path):
    df_existing = pd.read_csv(file_path)
    existing_ids = set(df_existing['id'].astype(str))
    print(f"📂 {len(existing_ids)} activités déjà enregistrées.")
else:
    df_existing = pd.DataFrame()
    existing_ids = set()
    print("📂 Aucune activité enregistrée, création d'un nouveau fichier.")

# Récupération des nouvelles activités
print("🔄 Récupération des nouvelles activités...")
request_page_num = 1
new_activities = []

while True:
    params = {'per_page': 200, 'page': request_page_num}
    response = requests.get(activities_url, headers=header, params=params).json()

    if not response:
        break  # Plus de nouvelles activités

    # Filtrer uniquement les nouvelles activités
    new_data = [activity for activity in response if str(activity['id']) not in existing_ids]
    
    if not new_data:
        break  # Plus rien à ajouter

    new_activities.extend(new_data)
    request_page_num += 1

    print(f"📥 Page {request_page_num} récupérée ({len(new_data)} nouvelles activités)")

    # Gestion des limites de requêtes API
    if request_page_num % 100 == 0:
        print("🚦 Pause de 15 minutes pour éviter le quota API...")
        time.sleep(900)  # Pause de 15 minutes

# Obtenir les détails de chaque activité
detailed_activities = []
for activity in new_activities:
    activity_id = activity['id']
    details = requests.get(f"{activity_details_url}{activity_id}", headers=header).json()
    
    # Ajouter toutes les infos détaillées
    activity.update(details)
    detailed_activities.append(activity)
    
    print(f"📊 Détails récupérés pour l'activité {activity_id}")

    # Pause pour éviter les quotas API (1 requête par seconde max)
    time.sleep(1)

# Ajout au CSV
if detailed_activities:
    df_new = pd.DataFrame(detailed_activities)
    df_final = pd.concat([df_existing, df_new], ignore_index=True)
    df_final.to_csv(file_path, index=False)
    print(f"✅ {len(detailed_activities)} nouvelles activités ajoutées avec détails dans {file_path}")
else:
    print("✅ Aucune nouvelle activité trouvée.")
