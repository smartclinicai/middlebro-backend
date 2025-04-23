from fastapi import FastAPI, Request, HTTPException, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, EmailStr
import pandas as pd
import os
import requests
from datetime import datetime, timedelta, date
from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy import insert, select

from db import database
from models import bookings, business_users
from calendar_integration import create_event

SECRET_KEY = "middlebro-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

oauth2_scheme = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(
    title="MiddleBro API",
    description="MiddleBro backend cu JWT, Calendar și rezervări automate",
    version="1.0.0"
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }
    for path in openapi_schema["paths"].values():
        for method in path.values():
            method.setdefault("security", [{"BearerAuth": []}])
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://middlebro.netlify.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.on_event("startup")
async def startup():
    print("🔌 Connecting to DB:", os.getenv("DATABASE_URL"))
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

@app.get("/")
def home():
    return {"message": "MiddleBro funcționează!"}
def get_next_date_for_weekday(weekday_name: str) -> str:
    days_map = {
        "luni": 0, "marți": 1, "miercuri": 2, "joi": 3,
        "vineri": 4, "sâmbătă": 5, "duminică": 6
    }
    today = date.today()
    target = days_map.get(weekday_name.lower())
    if target is None:
        raise ValueError(f"Zi invalidă: {weekday_name}")
    days_ahead = (target - today.weekday() + 7) % 7 or 7
    return (today + timedelta(days=days_ahead)).isoformat()

class MatchRequest(BaseModel):
    service: str
    city: str
    day: str
    hour: str
    email: str

def load_businesses_from_sheet():
    url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQg8KI_0G7imJNFCyzdwZdC3UkHfQxwTYDkdWfzfnB4IjDPJWr3uJdKlj6LI1g31BIweoPylMEHzskG/pub?output=csv"
    df = pd.read_csv(url)
    businesses = []
    for _, row in df.iterrows():
        businesses.append({
            "id": row["id"],
            "name": row["name"],
            "services": [s.strip() for s in row["services"].split(",")],
            "city": row["city"],
            "availability": {"joi": [h.strip() for h in row["joi"].split(",")]}
        })
    return businesses

@app.post("/match")
async def match_service(request: MatchRequest):
    for biz in load_businesses_from_sheet():
        if (
            request.service in biz["services"] and
            request.city.lower() == biz["city"].lower() and
            request.day in biz["availability"] and
            request.hour in biz["availability"][request.day]
        ):
            return {"match": biz}
    return {"match": None}

def send_email_mailersend(to_email, subject, html):
    url = "https://api.mailersend.com/v1/email"
    headers = {
        "Authorization": "Bearer mlsn.e11ff0706d2d5c341e1ad9042cfceefebcc4c540c6e7fea059b347b0ceff66ef",
        "Content-Type": "application/json"
    }
    payload = {
        "from": {"email": "test-eqvygm0z8rjl0p7w@mlsender.net", "name": "MiddleBro"},
        "to": [{"email": to_email}],
        "subject": subject,
        "html": html
    }
    requests.post(url, headers=headers, json=payload)

class BookingRequest(BaseModel):
    user_name: str
    business_id: str
    service: str
    date: str
    time: str
    email: str

@app.post("/book")
async def book_appointment(request: BookingRequest):
    date_iso = get_next_date_for_weekday(request.date)
    start = datetime.fromisoformat(f"{date_iso}T{request.time}")
    end = start + timedelta(hours=1)
    await database.execute(insert(bookings).values(
        user_name=request.user_name,
        business_id=request.business_id,
        service=request.service,
        date=request.date,
        time=request.time,
        created_at=datetime.now()
    ))
    send_email_mailersend(
        request.email,
        "📅 Rezervarea ta la MiddleBro",
        f"<p>Salut {request.user_name}, ai rezervat un {request.service} la {request.business_id} pentru {request.date}, ora {request.time}.</p>"
    )
    try:
        create_event(
            summary=f"{request.service} - {request.user_name}",
            description=f"La {request.business_id} prin MiddleBro",
            start_time=start.isoformat(),
            end_time=end.isoformat()
        )
    except Exception as e:
        print("Eroare calendar:", e)
    return {"status": "confirmed", "booking": request.dict()}

class RegisterBusinessRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = None

@app.post("/register_business")
async def register_business(request: RegisterBusinessRequest):
    existing = await database.fetch_one(select(business_users).where(business_users.c.email == request.email))
    if existing:
        return {"error": "Email deja înregistrat."}
    hashed = pwd_context.hash(request.password)
    await database.execute(insert(business_users).values(
        email=request.email,
        password_hash=hashed,
        name=request.name
    ))
    return {"status": "cont creat cu succes ✅"}

class LoginBusinessRequest(BaseModel):
    email: EmailStr
    password: str

def create_access_token(data: dict):
    data["exp"] = datetime.utcnow() + timedelta(minutes=60)
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

@app.post("/login_business")
async def login_business(request: LoginBusinessRequest):
    user = await database.fetch_one(select(business_users).where(business_users.c.email == request.email))
    if not user or not pwd_context.verify(request.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Email sau parolă incorectă.")
    token = create_access_token({"sub": request.email})
    return {"access_token": token, "token_type": "bearer"}

async def get_current_user(creds: HTTPAuthorizationCredentials = Security(oauth2_scheme)):
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalid.")
    user = await database.fetch_one(select(business_users).where(business_users.c.email == email))
    if not user:
        raise HTTPException(status_code=401, detail="Utilizator inexistent.")
    return user

@app.get("/my-profile", tags=["Autentificare"])
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    return {
        "email": current_user["email"],
        "name": current_user["name"],
        "created_at": current_user["created_at"]
    }
