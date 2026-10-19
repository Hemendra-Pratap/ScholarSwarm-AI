from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable fallback and safe defaults."""
    
    APP_NAME: str = "ScholarSwarm AI"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    
    # Server settings
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    
    # CORS Origins
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    
    # Database (configurable via DATABASE_URL, local SQLite default)
    DATABASE_URL: str = "sqlite:///./scholarswarm.db"
    
    # Document Ingestion limits
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MiB
    MAX_PDF_PAGES: int = 20
    MAX_DOCX_UNCOMPRESSED_BYTES: int = 30 * 1024 * 1024  # 30 MiB zip bomb protection
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
