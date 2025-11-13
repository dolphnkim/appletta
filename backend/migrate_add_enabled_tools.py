"""Migration script to add enabled_tools column to agents table"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from backend.db.session import engine

def migrate():
    """Add enabled_tools column to agents table"""
    print("Adding enabled_tools column to agents table...")

    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='agents' AND column_name='enabled_tools'
        """))

        if result.fetchone():
            print("⚠️  Column enabled_tools already exists, skipping migration")
            return

        # Add the column as JSONB, nullable
        conn.execute(text("""
            ALTER TABLE agents
            ADD COLUMN enabled_tools JSONB
        """))
        conn.commit()

        print("✅ Successfully added enabled_tools column")

if __name__ == "__main__":
    migrate()
