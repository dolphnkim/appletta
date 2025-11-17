"""Application configuration"""

import os
from pathlib import Path
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

    # API
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "Appletta"

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Model paths
    MODELS_DIR: str = os.getenv(
        "MODELS_DIR",
        str(Path.home() / ".cache" / "huggingface" / "hub")
    )
    ADAPTERS_DIR: str = os.getenv(
        "ADAPTERS_DIR",
        str(Path.home() / "appletta" / "adapters")
    )

    class Config:
        case_sensitive = True


settings = Settings()
