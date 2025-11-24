"""
Migration: Upgrade embedding vectors from 768 to 4096 dimensions

BACKGROUND:
We're switching from thenlper/gte-base (768 dims) to Qwen3-Embedding-8B (4096 dims).
This migration:
1. Alters the vector columns from Vector(768) to Vector(4096)
2. NULLs out existing embeddings (they need to be regenerated)

TABLES AFFECTED:
- messages.embedding
- journal_blocks.embedding
- rag_chunks.embedding

RUN:
    python backend/migrations/upgrade_embeddings_to_4096.py

IMPORTANT:
After this migration, run the re-embedding script to regenerate all embeddings
with the new Qwen3-Embedding model.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from backend.db.session import SessionLocal


def migrate():
    """Upgrade embedding columns from Vector(768) to Vector(4096)"""
    db = SessionLocal()

    try:
        print("=" * 60)
        print("Upgrading embedding vectors: 768 -> 4096 dimensions")
        print("=" * 60)

        # Step 1: Get counts of existing embeddings
        print("\n[1/4] Counting existing embeddings...")

        result = db.execute(text("SELECT COUNT(*) FROM messages WHERE embedding IS NOT NULL"))
        msg_count = result.scalar()
        print(f"  Messages with embeddings: {msg_count}")

        result = db.execute(text("SELECT COUNT(*) FROM journal_blocks WHERE embedding IS NOT NULL"))
        jb_count = result.scalar()
        print(f"  Journal blocks with embeddings: {jb_count}")

        result = db.execute(text("SELECT COUNT(*) FROM rag_chunks WHERE embedding IS NOT NULL"))
        rc_count = result.scalar()
        print(f"  RAG chunks with embeddings: {rc_count}")

        total = msg_count + jb_count + rc_count
        print(f"  TOTAL embeddings to regenerate: {total}")

        # Step 2: NULL out existing embeddings (they're incompatible with new dimension)
        print("\n[2/4] Clearing existing embeddings (will regenerate later)...")

        db.execute(text("UPDATE messages SET embedding = NULL WHERE embedding IS NOT NULL"))
        db.execute(text("UPDATE journal_blocks SET embedding = NULL WHERE embedding IS NOT NULL"))
        db.execute(text("UPDATE rag_chunks SET embedding = NULL WHERE embedding IS NOT NULL"))
        db.commit()
        print("  Done - all embeddings cleared")

        # Step 3: Drop the search_results view (depends on embedding columns)
        print("\n[3/6] Dropping search_results view...")
        db.execute(text("DROP VIEW IF EXISTS search_results"))
        db.commit()
        print("  Done")

        # Step 4: Drop ivfflat indexes (limited to 2000 dims)
        print("\n[4/6] Dropping ivfflat indexes (limited to 2000 dims)...")
        db.execute(text("DROP INDEX IF EXISTS idx_messages_embedding"))
        db.execute(text("DROP INDEX IF EXISTS idx_journal_blocks_embedding"))
        db.execute(text("DROP INDEX IF EXISTS idx_rag_chunks_embedding"))
        db.commit()
        print("  Done")

        # Step 5: Alter column types
        print("\n[5/6] Altering vector column dimensions...")

        # Messages
        print("  Altering messages.embedding...")
        db.execute(text("""
            ALTER TABLE messages
            ALTER COLUMN embedding TYPE vector(4096)
        """))

        # Journal blocks
        print("  Altering journal_blocks.embedding...")
        db.execute(text("""
            ALTER TABLE journal_blocks
            ALTER COLUMN embedding TYPE vector(4096)
        """))

        # RAG chunks
        print("  Altering rag_chunks.embedding...")
        db.execute(text("""
            ALTER TABLE rag_chunks
            ALTER COLUMN embedding TYPE vector(4096)
        """))

        db.commit()
        print("  Done - all columns upgraded to vector(4096)")

        # NOTE: pgvector HNSW/IVFFlat indexes are limited to 2000 dimensions.
        # For 4096-dim vectors, we use brute-force search (no index).
        # This is fine for small datasets (<10k records). For larger datasets,
        # consider dimensionality reduction or a smaller embedding model.
        print("\n[6/6] Skipping vector index (4096 dims > 2000 limit)...")
        print("  Using brute-force search (fine for <10k records)")
        print("  Done")

        # Recreate the search_results view with new dimension
        print("\nRecreating search_results view...")
        db.execute(text("""
            CREATE OR REPLACE VIEW search_results AS
            SELECT
                'rag_chunk'::text AS source_type,
                c.id,
                f.filename AS title,
                c.content AS snippet,
                c.created_at,
                c.embedding,
                c.content_tsv
            FROM rag_chunks c
            JOIN rag_files f ON c.file_id = f.id
            UNION ALL
            SELECT
                'journal_block'::text AS source_type,
                journal_blocks.id,
                journal_blocks.label AS title,
                journal_blocks.value AS snippet,
                journal_blocks.created_at,
                journal_blocks.embedding,
                journal_blocks.value_tsv AS content_tsv
            FROM journal_blocks
            UNION ALL
            SELECT
                'message'::text AS source_type,
                messages.id,
                messages.role AS title,
                messages.content AS snippet,
                messages.created_at,
                messages.embedding,
                messages.content_tsv
            FROM messages
        """))
        db.commit()
        print("  Done")

        # Verify
        print("\nVerifying changes...")

        # Check column types (PostgreSQL specific)
        result = db.execute(text("""
            SELECT table_name, column_name, udt_name
            FROM information_schema.columns
            WHERE column_name = 'embedding'
            AND table_name IN ('messages', 'journal_blocks', 'rag_chunks')
        """))
        for row in result:
            print(f"  {row[0]}.{row[1]}: {row[2]}")

        print("\n" + "=" * 60)
        print("MIGRATION COMPLETE!")
        print("=" * 60)
        print(f"\nNext steps:")
        print(f"  1. Start the Qwen embedding server:")
        print(f"     python backend/services/qwen_embedding_server.py")
        print(f"  2. Re-embed all data:")
        print(f"     python backend/migrations/reembed_all_data.py")

    except Exception as e:
        print(f"\n ERROR: Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
