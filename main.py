from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import pandas as pd
import os
import requests
from datetime import datetime, timedelta, date
import calendar
from passlib.context import CryptContext

from db import database
from models import bookings, business_users
from sqlalchemy import insert, select

from calendar_integration import create_event

app = FastAPI()

# 🔓 CORS pentru Netlify
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://middlebro.netlify.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔁 Conversie "joi" -> "2025-04-18"
def get_next_date_for_weekday(weekday_name: str) -> str:
    days_map = {
        "luni": 0,
        "marți": 1,
        "miercuri": 2,
        "joi": 3,
        "vineri": 4,
        "sâmbătă": 5,
        "duminică": 6
    }

    today = date.today()
    today_weekday = today.weekday()
    target_weekday = days_map.get(weekday_name.lower())

    if target_weekday is None:
        raise ValueError(f"Zi invalidă: {weekday_name}")

    days_ahead = (target_weekday - today_weekday + 7) % 7
    if days_ahead == 0:
        days_ahead = 7

    next_date = today + timedelta(days=days_ahead)
    return next_date.isoformat()

# 🔌 DB Connect
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

# 📌 Match endpoint
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

# 📩 Mailersend
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

# 🗓️ Booking
class BookingRequest(BaseModel):
    user_name: str
    business_id: str
    service: str
    date: str  # ex: joi
    time: str  # ex: 18:00
    email: str

@app.post("/book")
async def book_appointment(request: BookingRequest):
    try:
        # 🗓️ Transformăm "joi" în "2025-04-18"
        date_iso = get_next_date_for_weekday(request.date)
        start_dt = datetime.fromisoformat(f"{date_iso}T{request.time}")
        end_dt = start_dt + timedelta(hours=1)
    except Exception as e:
        return {"error": f"Data invalidă: {e}"}

    new_booking = {
        "user_name": request.user_name,
        "business_id": request.business_id,
        "service": request.service,
        "date": request.date,
        "time": request.time,
        "created_at": datetime.now(),
    }

    print("➔ Booking primit:", new_booking)

    try:
        query = insert(bookings).values(**new_booking)
        await database.execute(query)
        print("✅ Booking salvat cu succes în baza de date!")
    except Exception as e:
        print("❌ Eroare la salvare în DB:", e)

    # ✉️ Mail (momentan fail 422)
    send_email_mailersend(
        to_email=request.email,
        subject="🗓️ Rezervarea ta la MiddleBro",
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

    # 🗓️ Calendar
    try:
        create_event(
            summary=f"{request.service} - {request.user_name}",
            description=f"La {request.business_id} prin MiddleBro",
            start_time=start_dt.isoformat(),
            end_time=end_dt.isoformat()
        )
        print("🗓️ Eveniment adăugat în Google Calendar!")
    except Exception as e:
        print("❌ Eroare la adăugare în calendar:", e)

    return {"status": "confirmed", "booking": new_booking}

# 🔐 Register business endpoint
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class RegisterBusinessRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = None

@app.post("/register_business")
async def register_business(request: RegisterBusinessRequest):
    query = select(business_users).where(business_users.c.email == request.email)
    existing_user = await database.fetch_one(query)

    if existing_user:
        return {"error": "Email deja înregistrat."}

    hashed_password = pwd_context.hash(request.password)
    new_user = {
        "email": request.email,
        "password_hash": hashed_password,
        "name": request.name,
    }

    insert_query = insert(business_users).values(**new_user)
    await database.execute(insert_query)

    return {"status": "cont creat cu succes ✅"}
