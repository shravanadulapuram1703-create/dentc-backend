from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "DentC Backend"

    DATABASE_URL: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    dev_mode: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="allow"
    )


settings = Settings()