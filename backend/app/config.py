from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./cloudpulse.db"
    environment: str = "development"

    # OpenAI powers the chat assistant. Leave the key blank to disable chat
    # (the rest of the app works without it).
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Azure OpenAI: set the endpoint and key and every call goes to Azure instead.
    # On Azure the "model" settings below are your *deployment names*.
    azure_openai_endpoint: str = ""  # e.g. https://my-resource.openai.azure.com
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    # Set to false if your embedding deployment is text-embedding-ada-002, which
    # does not accept a `dimensions` argument (it is always 1536).
    embedding_supports_dimensions: bool = True
    # None = auto: send `temperature` only to gpt-4*/gpt-3.5* models (newer reasoning
    # models reject it). Force with LLM_SEND_TEMPERATURE=true/false.
    llm_send_temperature: bool | None = None
    # Which API the chat agent calls: "chat" (/chat/completions), "responses"
    # (/responses) or "auto" (chat for gpt-4*/gpt-3.5* models, responses for newer
    # reasoning models, which don't support function tools on /chat/completions).
    llm_chat_api: str = "auto"

    # RAG over the FinOps knowledge base (backend/knowledge/*.md).
    # embedding_dimensions must match the Vector column in the knowledge_chunks migration.
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    # A cheaper model is plenty for reranking passages and judging evals. Left blank,
    # these default to gpt-4o-mini on OpenAI, or to the chat deployment on Azure
    # (where gpt-4o-mini only exists if you deployed it).
    openai_rerank_model: str = ""
    openai_judge_model: str = ""
    rag_rerank: bool = True
    rag_candidates: int = 20  # per retriever, before fusion
    rag_top_k: int = 5  # passages handed to the chat model

    # Chat spends API credits, so each user gets a rolling hourly request budget.
    chat_requests_per_hour: int = 60
    # Prices for models not in llm.PRICING_PER_MTOK, as JSON in the env, e.g.
    # OPENAI_PRICING_OVERRIDES={"gpt-5": [1.25, 10.0]}  (USD per 1M input, output tokens)
    openai_pricing_overrides: dict[str, tuple[float, float]] = {}

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

    @property
    def embeddings_enabled(self) -> bool:
        """False when OPENAI_EMBEDDING_MODEL is blank: the knowledge base then runs on
        keyword search only (no embedding deployment needed)."""
        return bool(self.openai_embedding_model)

    @property
    def use_azure(self) -> bool:
        return bool(self.azure_openai_endpoint)

    @model_validator(mode="after")
    def _default_aux_models(self):
        fallback = self.openai_model if self.use_azure else "gpt-4o-mini"
        self.openai_rerank_model = self.openai_rerank_model or fallback
        self.openai_judge_model = self.openai_judge_model or fallback
        return self

    class Config:
        env_file = ".env"
        extra = "ignore"  # tolerate leftover/unused env vars instead of erroring


settings = Settings()