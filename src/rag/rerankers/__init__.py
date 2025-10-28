from src.config import settings
from src.rag.reranking.api_inference import InferenceAPIReranker
from src.rag.reranking.api_rerank_2 import InferenceAPIReranker2


def get_reranker():
    if settings.rerank_model == "nx-text-rerank-001":
        return InferenceAPIReranker(
            api_url=settings.rerank_url,
            api_key=settings.rerank_api_key,
        )
    elif settings.rerank_model == "nx-text-rerank-002":
        return InferenceAPIReranker2(
            api_url=settings.rerank_url,
            api_key=settings.rerank_api_key,
        )
    else:
        raise ValueError(f"Unsupported rerank model: {settings.rerank_model}")
