"""
Eenmalig uitvoeren om gmail_token.json te genereren.
Vereisten:
  - gmail_credentials.json in de root van het project (gedownload uit Google Cloud Console)
  - pip install google-auth-oauthlib
"""
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

flow = InstalledAppFlow.from_client_secrets_file("gmail_credentials.json", SCOPES)
print("Browser openen... (als dat niet lukt, kopieer de URL hieronder)")
creds = flow.run_local_server(port=8090, open_browser=True)

token_data = {
    "token":         creds.token,
    "refresh_token": creds.refresh_token,
    "token_uri":     creds.token_uri,
    "client_id":     creds.client_id,
    "client_secret": creds.client_secret,
    "scopes":        list(creds.scopes),
}

with open("gmail_token.json", "w") as f:
    json.dump(token_data, f, indent=2)

print("Klaar! gmail_token.json is aangemaakt.")
print("Zet de inhoud als GMAIL_TOKEN_JSON in Railway environment variables.")
