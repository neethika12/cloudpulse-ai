from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./cloudpulse.db"
    environment: str = "development"

    # Fully local AI - no API key or cloud account needed. Both models run
    # inside the backend container via Hugging Face transformers.
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chat_model: str = "google/flan-t5-base"

    # Optional - if unset, /api/anomalies/alert just reports that no webhook is configured.
    slack_webhook_url: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"  # tolerate leftover/unused env vars instead of erroring


settings = Settings()