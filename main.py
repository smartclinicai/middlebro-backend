from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import os
import requests
from datetime import datetime

from db import database
from models import bookings
from sqlalchemy import insert

app = FastAPI()

# 🔓 CORS pentru frontend (Netlify)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔌 Conectare la DB cu debug print
@app.on_event("startup")
async def startup():
    print("🔌 Connecting to DB:", os.getenv("DATABASE_URL"))
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# ✅ Health check
@app.get("/")
def home():
    return {"message": "MiddleBro funcționează!"}

# 📌 Match business endpoint
class MatchRequest(BaseModel):
    service: str
    city: str
    day: str
    hour: str
    email: str

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

# 📅 Booking endpoint
class BookingRequest(BaseModel):
    user_name: str
    business_id: str
    service: str
    date: str
    time: str
    email: str

@app.post("/book")
async def book_appointment(request: BookingRequest):
    new_booking = {
        "user_name": request.user_name,
        "business_id": request.business_id,
        "service": request.service,
        "date": request.date,
        "time": request.time,
        "created_at": datetime.now(),
    }

    print("➡️ Booking primit:", new_booking)

    try:
        query = insert(bookings).values(**new_booking)
        await database.execute(query)
        print("✅ Booking salvat cu succes în baza de date!")
    except Exception as e:
        print("❌ Eroare la salvare în DB:", e)

    # ✉️ Email
    api_key = os.getenv("BREVO_API_KEY")
    if api_key:
        try:
            response = requests.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "accept": "application/json",
                    "api-key": api_key,
                    "content-type": "application/json"
                },
                json={
                    "sender": {"name": "MiddleBro", "email": "no-reply@middlebro.ai"},
                    "to": [{"email": request.email}],
                    "subject": "📅 Rezervarea ta a fost confirmată",
                    "htmlContent": f"""
                    <html>
                        <body>
                            <h2>Salut, {request.user_name}!</h2>
                            <p>Ai rezervat cu succes un <strong>{request.service}</strong> la <strong>{request.business_id}</strong>.</p>
                            <p>📍 Data: {request.date}<br>⏰ Ora: {request.time}</p>
                            <br>
                            <p>Cu drag,<br><strong>MiddleBro 🤖</strong></p>
                        </body>
                    </html>
                    """
                }
            )
            print(f"📧 Email trimis: {response.status_code} | {response.text}")
        except Exception as e:
            print(f"❌ Eroare la trimiterea emailului: {str(e)}")
    else:
        print("❌ BREVO_API_KEY lipsă!")

    return {"status": "confirmed", "booking": new_booking}
