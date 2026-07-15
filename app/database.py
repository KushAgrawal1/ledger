from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Default connection URL matching your local Docker compose setup
DATABASE_URL = "postgresql+psycopg2://ledger:ledger@localhost:5432/ledger"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# This is the "Base" class that all your models inherit from
Base = declarative_base()

# Dependency to get DB session in FastAPI endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()