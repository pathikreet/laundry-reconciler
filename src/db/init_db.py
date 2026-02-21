from sqlalchemy import create_engine
from src.db.base import Base
import os

# Import all models to ensure they are registered with Base
from src.db import *

def init_db(db_path="laundry_reconciler.db"):
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    print(f"Database initialized at {db_path}")

if __name__ == "__main__":
    init_db()
