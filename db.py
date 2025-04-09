from databases import Database
from sqlalchemy import MetaData
import os

# Ia direct variabila de mediu (funcționează și local, și în producție)
DATABASE_URL = os.getenv("DATABASE_URL")

# Conectare la baza de date
database = Database(DATABASE_URL)

# Metadata pentru SQLAlchemy
metadata = MetaData()
