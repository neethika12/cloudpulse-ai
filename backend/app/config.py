from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./cloudpulse.db"
    environment: str = "development"

    class Config:
        env_file = ".env"


settings = Settings()