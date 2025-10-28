# src/rag/embeding/__init__.py
from src.config import settings
from src.rag.embeding.api_inference import InferenceAPIEmbeddings

embedding = InferenceAPIEmbeddings(
    api_url=settings.text_embedding_url,
    model_name=settings.text_embedding_model,
    api_key=settings.text_embedding_api_key,
)
