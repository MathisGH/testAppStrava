from flask import Flask, request, redirect
import requests
import json
import os

app = Flask(__name__)

CLIENT_ID = "152701"
CLIENT_SECRET = "f9994d3d0eac0d314a1ee9c94ccb2dd674debb5d"
REDIRECT_URI = "http://localhost:5000/callback"

ATHLETES_FILE = "athletes.json"

def load_athletes():
    if os.path.exists(ATHLETES_FILE):
        with open(ATHLETES_FILE, "r") as f:
            return json.load(f)
    return {"athletes": {}}

def save_athletes(data):
    with open(ATHLETES_FILE, "w") as f:
        json.dump(data, f, indent=4)

@app.route("/")
def home():
    """ Génère le lien d'autorisation pour un nouvel athlète """
    auth_url = (f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}"
                f"&redirect_uri={REDIRECT_URI}&response_type=code"
                f"&approval_prompt=force&scope=activity:read_all")
    return f"<h2>Autorisez l'accès à votre compte Strava :</h2><a href='{auth_url}'>Cliquez ici</a>"

@app.route("/callback")
def callback():
    """ Récupère le code d'autorisation et échange contre un token """
    code = request.args.get("code")
    if not code:
        return "Erreur : aucun code d'autorisation reçu."

    token_url = "https://www.strava.com/oauth/token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code"
    }

    response = requests.post(token_url, data=payload).json()

    if "access_token" not in response:
        return "Erreur : impossible d'obtenir un token."

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

    return f"✅ {athlete_info['firstname']} {athlete_info['lastname']} ajouté avec succès !"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Récupère le port de Render, sinon 5000 par défaut
    app.run(host="0.0.0.0", port=port, debug=True)