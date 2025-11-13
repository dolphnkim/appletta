"""Migration script to add is_template column to agents table"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from backend.db.session import engine

def migrate():
    """Add is_template column to agents table"""
    print("Adding is_template column to agents table...")

    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='agents' AND column_name='is_template'
        """))

        if result.fetchone():
            print("⚠️  Column is_template already exists, skipping migration")
            return

        # Add the column with default value False
        conn.execute(text("""
            ALTER TABLE agents
            ADD COLUMN is_template BOOLEAN NOT NULL DEFAULT FALSE
        """))
        conn.commit()

        print("✅ Successfully added is_template column")

if __name__ == "__main__":
    migrate()
