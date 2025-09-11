from typing import Literal
from dataclasses import dataclass
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from .settings import settings


class LLMModelConfigs(BaseModel):
    model: str
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.5


type SupportedLLMProviders = Literal[
    "nxchat", "nxchat-vision", "nxchat-vl-32b", "openai", "google-gemini", "claude"
]

LLM_MODELS = {
    "nxchat": ChatOpenAI,
    "nxchat-vision": ChatOpenAI,
    "openai": ChatOpenAI,
    "nxchat-vl-32b": ChatOpenAI,
    "google-gemini": ChatOpenAI,
    "claude": ChatOpenAI,
}

LLM_MODELS_CONFIG = {
    "nxchat": LLMModelConfigs(
        model="nxchat-internal",
        api_key=settings.ntqai_api_key,
        base_url=settings.ntqai_base_url,
    ),
    "nxchat-vision": LLMModelConfigs(
        model="nxchat-vision",
        api_key=settings.ntqai_api_key,
        base_url=settings.ntqai_base_url,
    ),
    "nxchat-vl-32b": LLMModelConfigs(
        model="qwen/qwen2.5-vl-32b-instruct:free",
        api_key=settings.ntqai_api_key,
        base_url=settings.ntqai_base_url,
    ),
    "claude": LLMModelConfigs(
        model="claude-3.5-haiku",
        api_key=settings.ntqai_api_key,
        base_url=settings.ntqai_base_url,
    ),
    "openai": LLMModelConfigs(
        model="gpt-5-mini",
        api_key=settings.ntqai_api_key,
        base_url=settings.ntqai_base_url,
    ),
    "google-gemini": LLMModelConfigs(
        model="google/gemini-2.0-flash-001",
        api_key=settings.ntqai_api_key,
        base_url=settings.ntqai_base_url,
    ),
}


@dataclass
class LangGraphRAGConfig:
    """Configuration for the RAG agent"""

    max_search_iterations: int = 5
    initial_top_k: int = 60
    initial_top_n: int = 15
    focused_top_k: int = 30
    focused_top_n: int = 10
    broader_top_k: int = 100
    broader_top_n: int = 20
    max_context_tokens: int = 16384
