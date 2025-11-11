#!/usr/bin/env python3
"""Test database connection and basic operations"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.db.session import engine
from backend.db.base import Base
from sqlalchemy import text

def test_connection():
    """Test basic database connection"""
    print("🔍 Testing database connection...")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"✅ Connected to PostgreSQL: {version.split(',')[0]}")
            return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

def test_extensions():
    """Test required extensions"""
    print("\n🔍 Testing extensions...")
    required_extensions = ['uuid-ossp', 'vector', 'pg_trgm']

    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT extname FROM pg_extension WHERE extname IN ('uuid-ossp', 'vector', 'pg_trgm')"
        ))
        installed = [row[0] for row in result]

        for ext in required_extensions:
            if ext in installed:
                print(f"✅ {ext} extension installed")
            else:
                print(f"❌ {ext} extension missing")

        return len(installed) == len(required_extensions)

def test_tables():
    """Test that all tables exist"""
    print("\n🔍 Testing tables...")
    required_tables = [
        'agents', 'rag_folders', 'rag_files', 'rag_chunks',
        'journal_blocks', 'conversations', 'messages'
    ]

    with engine.connect() as conn:
        result = conn.execute(text(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename IN ('agents', 'rag_folders', 'rag_files', 'rag_chunks',
                              'journal_blocks', 'conversations', 'messages')
            """
        ))
        installed = [row[0] for row in result]

        for table in required_tables:
            if table in installed:
                print(f"✅ {table} table exists")
            else:
                print(f"❌ {table} table missing")

        return len(installed) == len(required_tables)

def test_vector_operations():
    """Test vector operations"""
    print("\n🔍 Testing vector operations...")
    try:
        with engine.connect() as conn:
            # Test vector creation
            conn.execute(text("SELECT '[1,2,3]'::vector(3)"))
            print("✅ Vector type works")

            # Test cosine distance
            conn.execute(text("SELECT '[1,2,3]'::vector(3) <=> '[1,2,3]'::vector(3)"))
            print("✅ Cosine distance operator works")

            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Vector operations failed: {e}")
        return False

def main():
    print("=" * 60)
    print("Appletta Database Test Suite")
    print("=" * 60)

    results = []

    results.append(("Connection", test_connection()))
    results.append(("Extensions", test_extensions()))
    results.append(("Tables", test_tables()))
    results.append(("Vectors", test_vector_operations()))

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{name:20s} {status}")

    all_passed = all(r[1] for r in results)
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 All tests passed! Database is ready.")
    else:
        print("⚠️  Some tests failed. See errors above.")
    print("=" * 60)

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
