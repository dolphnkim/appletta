"""Migration: Rename system_instructions to project_instructions

Run this once to update the database schema to match the code.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from backend.db.session import SessionLocal

def migrate():
    """Rename system_instructions column to project_instructions"""
    db = SessionLocal()

    try:
        print("🔄 Renaming system_instructions column to project_instructions...")

        # Rename the column
        db.execute(text("""
            ALTER TABLE agents
            RENAME COLUMN system_instructions TO project_instructions
        """))

        db.commit()
        print("✅ Migration complete! Column renamed successfully.")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        print("Note: If column already renamed or doesn't exist, this is expected.")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
