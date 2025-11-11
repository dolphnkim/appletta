"""API routes for semantic and full-text search"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.db.session import get_db
from backend.schemas.rag import SearchQuery, SearchResponse, SearchResult

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.post("/", response_model=SearchResponse)
async def search(
    query: SearchQuery,
    db: Session = Depends(get_db)
):
    """Search across all content using full-text and/or semantic search

    Searches through:
    - RAG chunks (file contents)
    - Journal blocks
    - Conversation messages

    Returns results ranked by relevance.
    """

    if not query.semantic and not query.full_text:
        raise HTTPException(400, "At least one search method (semantic or full_text) must be enabled")

    results = []

    # Full-text search using PostgreSQL tsvector
    if query.full_text:
        # Build query filters
        where_clauses = []
        params = {"query": query.query, "limit": query.limit}

        if query.agent_id:
            where_clauses.append("agent_id = :agent_id")
            params["agent_id"] = str(query.agent_id)

        if query.source_types:
            placeholders = ','.join([f":source_type_{i}" for i in range(len(query.source_types))])
            where_clauses.append(f"source_type IN ({placeholders})")
            for i, source_type in enumerate(query.source_types):
                params[f"source_type_{i}"] = source_type

        where_clause = " AND " + " AND ".join(where_clauses) if where_clauses else ""

        # Full-text search query
        # Note: This searches the content_tsv column which is a generated tsvector
        fts_query = text(f"""
            SELECT
                id,
                source_type,
                title,
                snippet,
                created_at,
                ts_rank(content_tsv, plainto_tsquery('english', :query)) as score
            FROM search_results
            WHERE content_tsv @@ plainto_tsquery('english', :query)
            {where_clause}
            ORDER BY score DESC
            LIMIT :limit
        """)

        fts_results = db.execute(fts_query, params).fetchall()

        for row in fts_results:
            results.append(SearchResult(
                id=row.id,
                source_type=row.source_type,
                title=row.title,
                snippet=row.snippet[:500] if row.snippet else "",  # Truncate long snippets
                created_at=row.created_at,
                score=float(row.score),
            ))

    # TODO: Semantic search using embeddings
    # This requires:
    # 1. Embedding the query using the same model (thenlper/gte-base)
    # 2. Using pgvector cosine similarity search
    # 3. Merging with full-text results
    #
    # For now, we'll implement just full-text search
    # Semantic search will be added in the next iteration

    if query.semantic:
        # Placeholder for semantic search
        # This will be implemented when we add the embedding pipeline
        pass

    # Remove duplicates and sort by score
    seen_ids = set()
    unique_results = []
    for result in results:
        if result.id not in seen_ids:
            seen_ids.add(result.id)
            unique_results.append(result)

    # Sort by score
    unique_results.sort(key=lambda x: x.score, reverse=True)

    # Limit results
    unique_results = unique_results[:query.limit]

    return SearchResponse(
        results=unique_results,
        total=len(unique_results),
        query=query.query,
    )
