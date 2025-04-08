from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import json
from datetime import datetime
import requests

app = FastAPI()

# 🔓 Permite cereri de la orice origine (pentru Netlify)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "MiddleBro funcționează!"}

# 📄 Model pentru matching
class MatchRequest(BaseModel):
    service: str
    city: str
    day: str
    hour: str

# 📄 Model pentru rezervare
class BookingRequest(BaseModel):
    user_name: str
    business_id: str
    service: str
    date: str
    time: str
    email: str  # 🔥 nou! email din formular

# 🔄 Încarcă business-urile din Google Sheet
def load_businesses_from_sheet():
    sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQg8KI_0G7imJNFCyzdwZdC3UkHfQxwTYDkdWfzfnB4IjDPJWr3uJdKlj6LI1g31BIweoPylMEHzskG/pub?output=csv"
    df = pd.read_csv(sheet_url)

    businesses = []
    for _, row in df.iterrows():
        biz = {
            "id": row["id"],
            "name": row["name"],
            "services": [s.strip() for s in row["services"].split(",")],
            "city": row["city"],
            "availability": {
                "joi": [h.strip() for h in row["joi"].split(",")]
            }
        }
        businesses.append(biz)
    return businesses

# 🧠 Matching logic
@app.post("/match")
async def match_service(request: MatchRequest):
    businesses = load_businesses_from_sheet()

    for biz in businesses:
        if (
            request.service in biz["services"]
            and request.city.lower() == biz["city"].lower()
            and request.day in biz["availability"]
            and request.hour in biz["availability"][request.day]
        ):
            return {"match": biz}
    return {"match": None}

# ✉️ Trimite email cu Brevo
def send_confirmation_email(to_email, user_name, business_name, service, date, time):
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": "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",
        "content-type": "application/json"
    }
    payload = {
        "sender": { "name": "MiddleBro", "email": "noreply@middlebro.ai" },
        "to": [{ "email": to_email, "name": user_name }],
        "subject": "Rezervarea ta a fost confirmată – MiddleBro",
        "htmlContent": f"""
        <html>
          <body>
            <h2>Salut, {user_name}!</h2>
            <p>Rezervarea ta la <strong>{business_name}</strong> pentru <strong>{service}</strong> a fost confirmată.</p>
            <ul>
              <li><strong>Data:</strong> {date}</li>
              <li><strong>Ora:</strong> {time}</li>
            </ul>
            <p>📍 Locație: orașul selectat în platformă</p>
            <br />
            <p>Mulțumim că folosești <strong>MiddleBro</strong> – AI-ul tău pentru programări smart! 🤖</p>
          </body>
        </html>
        """
    }

    response = requests.post(url, json=payload, headers=headers)
    print(f"Email trimis: {response.status_code} | {response.text}")

# 📥 Rezervare + email
@app.post("/book")
def book_appointment(request: BookingRequest):
    new_booking = {
        "user_name": request.user_name,
        "business_id": request.business_id,
        "service": request.service,
        "date": request.date,
        "time": request.time,
        "email": request.email,
        "created_at": datetime.now().isoformat()
    }

    try:
        with open("bookings.json", "r") as f:
            existing = json.load(f)
    except:
        existing = []

    existing.append(new_booking)

    with open("bookings.json", "w") as f:
        json.dump(existing, f, indent=2)

    # 🔥 trimite emailul către userul real
    send_confirmation_email(
        to_email=request.email,
        user_name=request.user_name,
        business_name=request.business_id,
        service=request.service,
        date=request.date,
        time=request.time
    )

    return {"status": "confirmed", "booking": new_booking}
