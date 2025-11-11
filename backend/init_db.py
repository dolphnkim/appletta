"""Initialize the database with tables"""

from backend.db.base import Base
from backend.db.session import engine
from backend.db.models.agent import Agent  # Import to register the model

def init_db():
    """Create all database tables"""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Database initialized successfully!")

if __name__ == "__main__":
    init_db()
