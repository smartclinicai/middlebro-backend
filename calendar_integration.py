import datetime
import os
import pickle

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Scope-ul pentru acces Google Calendar
SCOPES = ['https://www.googleapis.com/auth/calendar']

def authenticate_google():
    creds = None

    # Dacă există un token salvat, îl folosim
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    # Dacă nu există sau a expirat, inițiem flow-ul manual
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES
            )

            # 🔗 Link de autentificare pentru server (Render)
            auth_url, _ = flow.authorization_url(prompt='consent')
            print(f"\n🔗 Deschide acest link într-un browser local:\n{auth_url}\n")
            code = input("📥 Introdu codul de autentificare de la Google: ")
            flow.fetch_token(code=code)
            creds = flow.credentials

        # Salvăm token-ul pentru folosiri viitoare
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    # Conectăm serviciul Calendar
    service = build('calendar', 'v3', credentials=creds)
    return service

def create_event(summary, description, start_time, end_time):
    service = authenticate_google()

    event = {
        'summary': summary,
        'description': description,
        'start': {
            'dateTime': start_time,
            'timeZone': 'Europe/Bucharest',
        },
        'end': {
            'dateTime': end_time,
            'timeZone': 'Europe/Bucharest',
        },
    }

    created_event = service.events().insert(calendarId='primary', body=event).execute()
    print(f'\n✅ Eveniment creat cu succes: {created_event.get("htmlLink")}\n')
