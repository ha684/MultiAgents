# src/llm/factory.py
from lagom import Container
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from parlant.core.loggers import Logger
from parlant.core.nlp.service import NLPService
from parlant.sdk import SDKError
from pydantic import SecretStr

from src.core.config.llm_config import (
    LLM_MODELS,
    LLM_MODELS_CONFIG,
    LLMModelConfigs,
    SupportedLLMProviders,
)
from src.llm.custom_openai_service import CustomOpenAIService


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


def openai(container: Container) -> NLPService:
    """Creates an OpenAI NLPService instance using the provided container."""
    if error := CustomOpenAIService.verify_environment():
        raise SDKError(error)

    return CustomOpenAIService(container[Logger])
