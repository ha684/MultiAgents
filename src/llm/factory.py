from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from src.config.llm_config import LLM_MODELS, LLM_MODELS_CONFIG, SupportedLLMProviders
from src.utils.logger_conf import logger


def get_llm(provider: SupportedLLMProviders) -> BaseChatModel:
    if provider not in LLM_MODELS:
        raise ValueError(f"Invalid provider: {provider}")

    logger.info(f"Initializing LLM for provider: {provider}")

    default_configs = LLM_MODELS_CONFIG.get(provider)
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


if __name__ == "__main__":
    # Example usage
    llm = get_llm("claude")
    print(f"Initialized LLM: {llm.invoke('Hello, world!')}")
    # You can now use `llm` to interact with the language model
