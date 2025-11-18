"""Migration: Add router_logging_enabled column to agents

Run this once to update the database schema to match the code.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from backend.db.session import SessionLocal

def migrate():
    """Add router_logging_enabled column to agents table"""
    db = SessionLocal()

    try:
        print("🔄 Adding router_logging_enabled column to agents...")

        # Add the column with default value of false
        db.execute(text("""
            ALTER TABLE agents
            ADD COLUMN IF NOT EXISTS router_logging_enabled BOOLEAN DEFAULT FALSE
        """))

        db.commit()
        print("✅ Migration complete! Column added successfully.")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        print("Note: If column already exists, this is expected.")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
