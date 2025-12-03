# src/llm/factory.py
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.core.config.llm_config import (
    LLM_MODELS,
    LLM_MODELS_CONFIG,
    LLMModelConfigs,
    SupportedLLMProviders,
)


def get_llm(
    provider: SupportedLLMProviders, config: LLMModelConfigs | None = None
) -> BaseChatModel:
    if provider not in LLM_MODELS:
        raise ValueError(f"Invalid provider: {provider}")

    default_configs = config or LLM_MODELS_CONFIG.get(provider)
    assert default_configs is not None, f"Configs for provider {provider} not found"
    baseModel = LLM_MODELS.get(provider, ChatOpenAI)

    if not default_configs.api_key:
        raise ValueError("API key is required for OpenAI provider")

    return baseModel(
        model=default_configs.model,
        api_key=SecretStr(default_configs.api_key),
        base_url=default_configs.base_url,
        temperature=default_configs.temperature,
    )
