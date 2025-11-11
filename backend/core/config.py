"""Application configuration"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Database - PostgreSQL with pgvector for embeddings
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"postgresql://{os.getenv('USER', 'postgres')}@localhost/appletta"
    )

    # Vector dimensions (must match embedding model)
    EMBEDDING_DIMENSIONS: int = 768

    # Memory coordinator model (Qwen2.5-3B for memory selection)
    MEMORY_COORDINATOR_MODEL_PATH: str = os.getenv(
        "MEMORY_COORDINATOR_MODEL_PATH",
        ""  # Default empty, user must configure
    )
    MEMORY_COORDINATOR_PORT: int = 8002  # Dedicated port for memory coordinator

    # API
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "Appletta"

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    class Config:
        case_sensitive = True


settings = Settings()
