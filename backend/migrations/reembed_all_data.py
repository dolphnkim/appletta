"""
Re-embed all data with Qwen3-Embedding-8B

PURPOSE:
After migrating the database to 4096-dimension vectors, this script regenerates
all embeddings using the new Qwen3-Embedding-8B model.

PREREQUISITES:
1. Run upgrade_embeddings_to_4096.py first
2. Start the Qwen embedding server:
   python backend/services/qwen_embedding_server.py

RUN:
    python backend/migrations/reembed_all_data.py

This will re-embed:
- All messages in conversations
- All journal blocks
- All RAG chunks
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from backend.db.session import SessionLocal
from backend.services.qwen_embedding_client import get_embedding_client
from backend.services.keyword_extraction import extract_keywords


def reembed_all():
    """Re-embed all data with Qwen3-Embedding-8B"""
    db = SessionLocal()
    client = get_embedding_client()

    # Check if server is available
    if not client.is_server_available():
        print("ERROR: Qwen embedding server not available!")
        print("Start it with: python backend/services/qwen_embedding_server.py")
        return

    try:
        print("=" * 60)
        print("Re-embedding all data with Qwen3-Embedding-8B")
        print("=" * 60)

        # ================================================================
        # Messages
        # ================================================================
        print("\n[1/3] Re-embedding messages...")

        result = db.execute(text("""
            SELECT id, content, metadata
            FROM messages
            WHERE content IS NOT NULL AND content != ''
        """))
        messages = result.fetchall()
        print(f"  Found {len(messages)} messages to embed")

        for i, (msg_id, content, metadata) in enumerate(messages):
            try:
                # Get tags from metadata if available
                tags = []
                if metadata and isinstance(metadata, dict):
                    tags = metadata.get("tags", [])

                # Embed with tags
                embedding = client.embed_with_tags(content, tags)

                # Update database
                db.execute(
                    text("UPDATE messages SET embedding = :embedding WHERE id = :id"),
                    {"embedding": str(embedding), "id": str(msg_id)}
                )

                if (i + 1) % 10 == 0:
                    db.commit()
                    print(f"  Processed {i + 1}/{len(messages)} messages")

            except Exception as e:
                print(f"  WARNING: Failed to embed message {msg_id}: {e}")
                continue

        db.commit()
        print(f"  Done - embedded {len(messages)} messages")

        # ================================================================
        # Journal Blocks
        # ================================================================
        print("\n[2/3] Re-embedding journal blocks...")

        result = db.execute(text("""
            SELECT id, label, value, metadata
            FROM journal_blocks
            WHERE value IS NOT NULL AND value != ''
        """))
        blocks = result.fetchall()
        print(f"  Found {len(blocks)} journal blocks to embed")

        for i, (block_id, label, value, metadata) in enumerate(blocks):
            try:
                # Combine label and value for richer embedding
                full_text = f"{label}: {value}" if label else value

                # Get tags from metadata if available
                tags = []
                if metadata and isinstance(metadata, dict):
                    tags = metadata.get("tags", [])

                # If no tags, extract some
                if not tags:
                    tags = extract_keywords(full_text, max_keywords=5)

                # Embed with tags
                embedding = client.embed_with_tags(full_text, tags)

                # Update database
                db.execute(
                    text("UPDATE journal_blocks SET embedding = :embedding WHERE id = :id"),
                    {"embedding": str(embedding), "id": str(block_id)}
                )

                if (i + 1) % 10 == 0:
                    db.commit()
                    print(f"  Processed {i + 1}/{len(blocks)} journal blocks")

            except Exception as e:
                print(f"  WARNING: Failed to embed journal block {block_id}: {e}")
                continue

        db.commit()
        print(f"  Done - embedded {len(blocks)} journal blocks")

        # ================================================================
        # RAG Chunks
        # ================================================================
        print("\n[3/3] Re-embedding RAG chunks...")

        result = db.execute(text("""
            SELECT id, content, metadata
            FROM rag_chunks
            WHERE content IS NOT NULL AND content != ''
        """))
        chunks = result.fetchall()
        print(f"  Found {len(chunks)} RAG chunks to embed")

        for i, (chunk_id, content, metadata) in enumerate(chunks):
            try:
                # Get tags from metadata if available
                tags = []
                if metadata and isinstance(metadata, dict):
                    tags = metadata.get("tags", [])

                # Embed with tags
                embedding = client.embed_with_tags(content, tags)

                # Update database
                db.execute(
                    text("UPDATE rag_chunks SET embedding = :embedding WHERE id = :id"),
                    {"embedding": str(embedding), "id": str(chunk_id)}
                )

                if (i + 1) % 10 == 0:
                    db.commit()
                    print(f"  Processed {i + 1}/{len(chunks)} RAG chunks")

            except Exception as e:
                print(f"  WARNING: Failed to embed RAG chunk {chunk_id}: {e}")
                continue

        db.commit()
        print(f"  Done - embedded {len(chunks)} RAG chunks")

        # ================================================================
        # Summary
        # ================================================================
        print("\n" + "=" * 60)
        print("RE-EMBEDDING COMPLETE!")
        print("=" * 60)
        print(f"  Messages: {len(messages)}")
        print(f"  Journal blocks: {len(blocks)}")
        print(f"  RAG chunks: {len(chunks)}")
        print(f"  TOTAL: {len(messages) + len(blocks) + len(chunks)}")

    except Exception as e:
        print(f"\nERROR: Re-embedding failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()
        client.close()


if __name__ == "__main__":
    reembed_all()
