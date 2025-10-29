# src/rag/graph/graphity_client.py
from graphiti_core import Graphiti
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client import LLMConfig, OpenAIClient

from src.core.config.settings import settings
from src.rag.graph.custom_reranker import CustomRerankerClient

llm_config = LLMConfig(
    small_model=settings.ntqai_model,
    model=settings.ntqai_model,
    base_url=settings.ntqai_base_url,
    api_key=settings.ntqai_api_key,
)

embedding_config = OpenAIEmbedderConfig(
    embedding_model=settings.text_embedding_model,
    api_key=settings.text_embedding_api_key,
    base_url=settings.text_embedding_url,
)

graphiti = Graphiti(
    settings.neo4j_uri,
    settings.neo4j_user,
    settings.neo4j_password,
    llm_client=OpenAIClient(
        config=llm_config,
    ),
    embedder=OpenAIEmbedder(
        config=embedding_config,
    ),
    cross_encoder=CustomRerankerClient(
        config=llm_config,
    ),
)
