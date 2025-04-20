from flask import Flask, request, redirect, jsonify, send_file # type: ignore
import requests
import json
import os
from dotenv import load_dotenv # type: ignore
load_dotenv()  # Charger les variables d'environnement depuis le fichier .env

app = Flask(__name__)

CLIENT_ID = "152701"
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET") # Token secret Strava à récupérer dans le dossier .env
REDIRECT_URI = "https://testappstrava.onrender.com/callback"

ATHLETES_FILE = "athletes.json"

def load_athletes(): # Charge les athlètes depuis le fichier JSON
    if os.path.exists(ATHLETES_FILE):
        with open(ATHLETES_FILE, "r") as f:
            return json.load(f)
    return {"athletes": {}}

def save_athletes(data): # Sauvegarde les athlètes dans le fichier JSON
    with open(ATHLETES_FILE, "w") as f:
        json.dump(data, f, indent=4)
    print("Fichier athletes.json mis à jour")

@app.route("/")
def home():
    """ Génère le lien d'autorisation Strava """
    auth_url = (f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}"
                f"&redirect_uri={REDIRECT_URI}&response_type=code"
                f"&approval_prompt=force&scope=activity:read_all")
    return f"<h2>Autorisez l'accès à votre compte Strava :</h2><a href='{auth_url}'>Cliquez ici</a>"

@app.route("/callback")
def callback():
    """ Récupère le code d'autorisation et échange contre un token """
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

    # Obtenir les infos de l'athlète
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

    # Sauvegarde dans le fichier JSON
    data = load_athletes()
    data["athletes"][athlete_id] = athlete_info
    save_athletes(data)

    return f"{athlete_info['firstname']} {athlete_info['lastname']} ajouté avec succès !"

@app.route("/athletes")
def get_athletes():
    """ Retourne la liste des athlètes enregistrés """
    data = load_athletes()
    return jsonify(data)

@app.route("/download_athletes")
def download_athletes():
    """ Permet de télécharger le fichier athletes.json """
    return send_file(ATHLETES_FILE, as_attachment=True)

# if __name__ == "__main__":
#     port = int(os.environ.get("PORT", 5000))  # Récupère le port de Render, sinon 5000 par défaut
#     app.run(host="0.0.0.0", port=port, debug=True)
