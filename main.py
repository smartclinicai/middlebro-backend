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

# 📩 Funcția de trimitere email prin Mailersend
def send_email_mailersend(to_email, subject, html_content):
    url = "https://api.mailersend.com/v1/email"
    headers = {
        "Authorization": "Bearer mlsn.e11ff0706d2d5c341e1ad9042cfceefebcc4c540c6e7fea059b347b0ceff66ef",
        "Content-Type": "application/json"
    }
    json_data = {
        "from": {
            "email": "test-eqvygm0z8rjl0p7w@mlsender.net",
            "name": "MiddleBro"
        },
        "to": [
            {
                "email": to_email,
                "name": "Client"
            }
        ],
        "subject": subject,
        "html": html_content
    }

    response = requests.post(url, headers=headers, json=json_data)
    print(f"📬 Mail trimis cu status {response.status_code} | {response.text}")

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

    # ✉️ Trimitem email cu Mailersend
    send_email_mailersend(
        to_email=request.email,
        subject="📅 Rezervarea ta la MiddleBro",
        html_content=f"""
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
    )

    return {"status": "confirmed", "booking": new_booking}
