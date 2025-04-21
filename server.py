from flask import Flask, request, redirect, jsonify, send_file  # type: ignore
import requests
import json
import os
import pandas as pd
import gspread
from dotenv import load_dotenv  # type: ignore
from oauth2client.service_account import ServiceAccountCredentials
from io import StringIO

load_dotenv()  # Charger les variables d'environnement depuis le fichier .env

app = Flask(__name__)

CLIENT_ID = "152701"
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REDIRECT_URI = "https://testappstrava.onrender.com/callback"
# REDIRECT_URI = "http://localhost:5000/callback"

ATHLETES_FILE = "athletes.json"
GOOGLE_SHEET_NAME = "Athletes Strava"

# --- Définition du scope et chargement du service account depuis Render ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT")
creds_dict = json.loads(SERVICE_ACCOUNT_JSON)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

def load_athletes():
    if os.path.exists(ATHLETES_FILE):
        with open(ATHLETES_FILE, "r") as f:
            return json.load(f)
    return {"athletes": {}}

def save_athletes(data):
    with open(ATHLETES_FILE, "w") as f:
        json.dump(data, f, indent=4)
    print("Fichier athletes.json mis à jour")

def save_to_google_sheets(athletes_data):
    try:
        print("Connexion à Google Sheets...")
        client = gspread.authorize(creds)

        print("Ouverture de la feuille...")
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        sheet.clear()

        print("Préparation des données...")
        rows = []
        for athlete_id, info in athletes_data["athletes"].items():
            row = {
                "id": athlete_id,
                "firstname": info.get("firstname"),
                "lastname": info.get("lastname"),
                "access_token": info.get("access_token"),
                "refresh_token": info.get("refresh_token")
            }
            rows.append(row)

        df = pd.DataFrame(rows)
        print("Mise à jour de la feuille...")
        sheet.update([df.columns.values.tolist()] + df.values.tolist())

        print("Données envoyées à Google Sheets")
    except Exception as e:
        print(f"Erreur lors de l'envoi à Google Sheets : {e}")

@app.route("/")
def home():
    auth_url = (f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}"
                f"&redirect_uri={REDIRECT_URI}&response_type=code"
                f"&approval_prompt=force&scope=activity:read_all")
    return f"<h2>Autorisez l'accès à votre compte Strava :</h2><a href='{auth_url}'>Cliquez ici</a>"

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Erreur : Aucun code reçu."

    token_url = "https://www.strava.com/oauth/token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code"
    }

    response = requests.post(token_url, data=payload).json()

    if "access_token" not in response:
        return "Erreur : Impossible d'obtenir un token."

    access_token = response["access_token"]
    refresh_token = response["refresh_token"]
    athlete = requests.get("https://www.strava.com/api/v3/athlete",
                           headers={"Authorization": f"Bearer {access_token}"}).json()

    athlete_id = str(athlete["id"])
    athlete_info = {
        "firstname": athlete.get("firstname", "unknown"),
        "lastname": athlete.get("lastname", "unknown"),
        "access_token": access_token,
        "refresh_token": refresh_token
    }

    data = load_athletes()
    data["athletes"][athlete_id] = athlete_info
    save_athletes(data)
    save_to_google_sheets(data)

    return f"{athlete_info['firstname']} {athlete_info['lastname']} ajouté avec succès !"

@app.route("/athletes")
def get_athletes():
    data = load_athletes()
    return jsonify(data)

@app.route("/download_athletes")
def download_athletes():
    return send_file(ATHLETES_FILE, as_attachment=True)

# Décommenter ceci pour exécuter en local :
# if __name__ == "__main__":
#     port = int(os.environ.get("PORT", 5000))
#     app.run(host="0.0.0.0", port=port, debug=True)
