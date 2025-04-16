from dotenv import load_dotenv
load_dotenv()

import os
from databases import Database
from sqlalchemy import MetaData

DATABASE_URL = os.getenv("DATABASE_URL")
database = Database(DATABASE_URL)
metadata = MetaData()
