from sqlalchemy import Table, Column, Integer, String, DateTime
from sqlalchemy.sql import func
from db import metadata

# 🗓️ Tabela de rezervări
bookings = Table(
    "bookings",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_name", String(255), nullable=False),
    Column("business_id", String(255), nullable=False),
    Column("service", String(255), nullable=False),
    Column("date", String(255), nullable=False),
    Column("time", String(255), nullable=False),
    Column("created_at", DateTime, default=func.now(), nullable=False),
)

# 👤 Tabela de utilizatori business
business_users = Table(
    "business_users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String(255), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("name", String(255), nullable=True),
    Column("created_at", DateTime, default=func.now(), nullable=False),
)
