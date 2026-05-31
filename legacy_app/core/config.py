from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "DentC Backend"

    DATABASE_URL: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    dev_mode: bool = False

    
    # Redis (ADD THIS)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    
    # Google Cloud / Vertex AI
    GOOGLE_CLOUD_PROJECT_ID: str | None = None
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    GEMINI_MODEL_NAME: str = "gemini-2.5-pro"


    model_config = SettingsConfigDict(
        env_file=".env",
        extra="allow"
    )


settings = Settings()