from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.models import OAuthFlows as OAuthFlowsModel
from fastapi.security import OAuth2
from pydantic import BaseModel, EmailStr
from fastapi.security import OAuth2PasswordBearer
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

class OAuth2PasswordBearerWithCookie(OAuth2):
    def __init__(self, tokenUrl: str):
        flows = OAuthFlowsModel(password={"tokenUrl": tokenUrl})
        super().__init__(flows=flows)

oauth2_scheme = OAuth2PasswordBearerWithCookie(tokenUrl="login_business")

SECRET_KEY = "middlebro-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(
    title="MiddleBro API",
    description="MiddleBro backend cu autentificare parteneri și rute securizate 🔐",
    version="1.0.0",
    swagger_ui_init_oauth={
        "usePkceWithAuthorizationCodeGrant": False
    }
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://middlebro.netlify.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
# 🔁 Conversie zi → ISO format
def get_next_date_for_weekday(weekday_name: str) -> str:
    days_map = {
        "luni": 0, "marți": 1, "miercuri": 2,
        "joi": 3, "vineri": 4, "sâmbătă": 5, "duminică": 6
    }
    today = date.today()
    target_weekday = days_map.get(weekday_name.lower())
    if target_weekday is None:
        raise ValueError(f"Zi invalidă: {weekday_name}")
    days_ahead = (target_weekday - today.weekday() + 7) % 7 or 7
    return (today + timedelta(days=days_ahead)).isoformat()

# 📌 Matching
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

# 📩 Email
def send_email_mailersend(to_email, subject, html_content):
    url = "https://api.mailersend.com/v1/email"
    headers = {
        "Authorization": "Bearer mlsn.e11ff0706d2d5c341e1ad9042cfceefebcc4c540c6e7fea059b347b0ceff66ef",
        "Content-Type": "application/json"
    }
    data = {
        "from": {"email": "test-eqvygm0z8rjl0p7w@mlsender.net", "name": "MiddleBro"},
        "to": [{"email": to_email}],
        "subject": subject,
        "html": html_content
    }
    requests.post(url, headers=headers, json=data)

# 📅 Booking
class BookingRequest(BaseModel):
    user_name: str
    business_id: str
    service: str
    date: str
    time: str
    email: str

@app.post("/book")
async def book_appointment(request: BookingRequest):
    try:
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
        "created_at": datetime.now()
    }

    try:
        await database.execute(insert(bookings).values(**new_booking))
    except Exception as e:
        print("❌ Eroare DB:", e)

    send_email_mailersend(
        request.email,
        "🗓️ Rezervarea ta la MiddleBro",
        f"<p>Salut, {request.user_name}!</p><p>Ai rezervat un {request.service} la {request.business_id} pentru {request.date} la {request.time}.</p><p><strong>MiddleBro 🤖</strong></p>"
    )

    try:
        create_event(
            summary=f"{request.service} - {request.user_name}",
            description=f"La {request.business_id} prin MiddleBro",
            start_time=start_dt.isoformat(),
            end_time=end_dt.isoformat()
        )
    except Exception as e:
        print("❌ Eroare calendar:", e)

    return {"status": "confirmed", "booking": new_booking}
# 🔐 REGISTER & LOGIN
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
    await database.execute(insert(business_users).values(**new_user))
    return {"status": "cont creat cu succes ✅"}

class LoginBusinessRequest(BaseModel):
    email: EmailStr
    password: str

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=60))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

@app.post("/login_business")
async def login_business(request: LoginBusinessRequest):
    query = select(business_users).where(business_users.c.email == request.email)
    user = await database.fetch_one(query)
    if not user or not pwd_context.verify(request.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Email sau parolă incorectă.")
    token = create_access_token({"sub": request.email})
    return {"access_token": token, "token_type": "bearer"}

# 🔒 JWT Auth Helper
async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Token invalid.")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalid.")
    user = await database.fetch_one(select(business_users).where(business_users.c.email == email))
    if user is None:
        raise HTTPException(status_code=401, detail="Utilizator inexistent.")
    return user

# ✅ RUTA PROTEJATĂ
@app.get("/my-profile")
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    return {
        "email": current_user["email"],
        "name": current_user["name"],
        "created_at": current_user["created_at"]
    }
