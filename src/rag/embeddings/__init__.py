# src/rag/embeding/__init__.py
from src.core.config.settings import settings
from src.rag.embeddings.api_inference import InferenceAPIEmbeddings, RagasSyncEmbeddings

embedding = InferenceAPIEmbeddings(
    api_url=settings.text_embedding_url,
    model_name=settings.text_embedding_model,
    api_key=settings.text_embedding_api_key,
)

ragas_embedding = RagasSyncEmbeddings(
    api_url=settings.text_embedding_url,
    api_key=settings.text_embedding_api_key,
    model_name=settings.text_embedding_model,
)
