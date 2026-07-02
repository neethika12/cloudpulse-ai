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

    # Auth - change jwt_secret_key for any real deployment. It's fine as a default
    # for local dev since tokens only ever leave this machine.
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Symmetric key used to encrypt AWS secret access keys at rest. Generate a real
    # one for anything beyond local dev:
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    app_encryption_key: str = "HicjRZLuUYNG8mY1YeYDN5WbfeESSC5ovmp793lVLrU="

    class Config:
        env_file = ".env"
        extra = "ignore"  # tolerate leftover/unused env vars instead of erroring


settings = Settings()