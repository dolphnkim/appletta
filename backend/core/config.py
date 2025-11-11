"""Application configuration"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Database
    DATABASE_URL: str = "sqlite:///./appletta.db"

    # API
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "Appletta"

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    class Config:
        case_sensitive = True


settings = Settings()
