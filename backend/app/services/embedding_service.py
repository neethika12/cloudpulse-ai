from langchain_huggingface import HuggingFaceEmbeddings
from app.config import settings

# Runs locally inside the container - no API key needed.
# Model weights (~90MB) download from Hugging Face on first use and are cached.
_embeddings = HuggingFaceEmbeddings(model_name=settings.embedding_model)


def embed_text(text: str) -> list[float]:
    return _embeddings.embed_query(text)
