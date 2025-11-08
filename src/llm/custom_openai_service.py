# src/llm/custom_openai_service.py

from __future__ import annotations
import json
import time
from typing import Any, Mapping

import jsonfinder
from openai import (
    APIConnectionError,
    APIResponseValidationError,
    APITimeoutError,
    AsyncClient,
    ConflictError,
    InternalServerError,
    RateLimitError,
)
from parlant.adapters.nlp.common import normalize_json_output
from parlant.core.engines.alpha.prompt_builder import PromptBuilder
from parlant.core.loggers import LogLevel, Logger
from parlant.core.nlp.embedding import Embedder, EmbeddingResult
from parlant.core.nlp.generation import SchematicGenerationResult, SchematicGenerator, T
from parlant.core.nlp.generation_info import GenerationInfo, UsageInfo
from parlant.core.nlp.moderation import ModerationCheck, ModerationService
from parlant.core.nlp.policies import policy, retry
from parlant.core.nlp.service import NLPService
from parlant.core.nlp.tokenization import EstimatingTokenizer
from pydantic import ValidationError
import tiktoken
from typing_extensions import override

from src.core.config.settings import settings


RATE_LIMIT_ERROR_MESSAGE = (
    "NTQAI API rate limit exceeded. Possible reasons:\n"
    "1. Your account may have insufficient API credits.\n"
    "2. You may be using a free-tier account with limited request capacity.\n"
    "3. You might have exceeded the requests-per-minute limit for your account.\n\n"
    "Recommended actions:\n"
    "- Check your NTQAI account balance and billing status.\n"
    "- Review your API usage limits in NTQAI's dashboard.\n"
)


class CustomOpenAIEstimatingTokenizer(EstimatingTokenizer):
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        # Fallback to a compatible tokenizer if custom model not available
        try:
            self.encoding = tiktoken.encoding_for_model(model_name)
        except KeyError:
            # Use gpt-4o tokenizer as fallback for custom models
            self.encoding = tiktoken.encoding_for_model("gpt-4o")

    @override
    async def estimate_token_count(self, prompt: str) -> int:
        tokens = self.encoding.encode(prompt)
        return len(tokens)


class CustomOpenAISchematicGenerator(SchematicGenerator[T]):
    supported_openai_params = ["temperature", "logit_bias", "max_tokens"]
    supported_hints = supported_openai_params + ["strict"]

    def __init__(
        self,
        model_name: str,
        logger: Logger,
        base_url: str,
        api_key: str,
        tokenizer_model_name: str | None = None,
    ) -> None:
        self.model_name = model_name
        self._logger = logger
        self._base_url = base_url
        self._api_key = api_key

        self._client = AsyncClient(
            api_key=api_key,
            base_url=base_url,
        )

        self._tokenizer = CustomOpenAIEstimatingTokenizer(
            model_name=tokenizer_model_name or self.model_name
        )

    @property
    @override
    def id(self) -> str:
        return f"ntqai/{self.model_name}"

    @property
    @override
    def tokenizer(self) -> CustomOpenAIEstimatingTokenizer:
        return self._tokenizer

    @policy(
        [
            retry(
                exceptions=(
                    APIConnectionError,
                    APITimeoutError,
                    ConflictError,
                    RateLimitError,
                    APIResponseValidationError,
                ),
            ),
            retry(InternalServerError, max_exceptions=2, wait_times=(1.0, 5.0)),
        ]
    )
    @override
    async def generate(
        self,
        prompt: str | PromptBuilder,
        hints: Mapping[str, Any] = {},
    ) -> SchematicGenerationResult[T]:
        with self._logger.scope("CustomOpenAISchematicGenerator"):
            with self._logger.operation(
                f"LLM Request ({self.schema.__name__})", level=LogLevel.TRACE
            ):
                return await self._do_generate(prompt, hints)

    async def _do_generate(
        self,
        prompt: str | PromptBuilder,
        hints: Mapping[str, Any] = {},
    ) -> SchematicGenerationResult[T]:
        if isinstance(prompt, PromptBuilder):
            prompt = prompt.build()

        openai_api_arguments = {
            k: v for k, v in hints.items() if k in self.supported_openai_params
        }

        if hints.get("strict", False):
            t_start = time.time()
            try:
                response = await self._client.beta.chat.completions.parse(
                    messages=[{"role": "developer", "content": prompt}],
                    model=self.model_name,
                    response_format=self.schema,
                    **openai_api_arguments,
                )
            except RateLimitError:
                self._logger.error(RATE_LIMIT_ERROR_MESSAGE)
                raise

            t_end = time.time()

            if response.usage:
                self._logger.trace(response.usage.model_dump_json(indent=2))

            parsed_object = response.choices[0].message.parsed
            assert parsed_object

            assert response.usage

            # prompt_tokens_details might not be available in custom APIs
            cached_tokens = 0
            if (
                hasattr(response.usage, "prompt_tokens_details")
                and response.usage.prompt_tokens_details
            ):
                cached_tokens = response.usage.prompt_tokens_details.cached_tokens or 0

            return SchematicGenerationResult[T](
                content=parsed_object,
                info=GenerationInfo(
                    schema_name=self.schema.__name__,
                    model=self.id,
                    duration=(t_end - t_start),
                    usage=UsageInfo(
                        input_tokens=response.usage.prompt_tokens,
                        output_tokens=response.usage.completion_tokens,
                        extra={"cached_input_tokens": cached_tokens},
                    ),
                ),
            )

        else:
            try:
                t_start = time.time()
                response = await self._client.chat.completions.create(
                    messages=[{"role": "developer", "content": prompt}],
                    model=self.model_name,
                    response_format={"type": "json_object"},
                    **openai_api_arguments,
                )
                t_end = time.time()
            except RateLimitError:
                self._logger.error(RATE_LIMIT_ERROR_MESSAGE)
                raise

            if response.usage:
                self._logger.trace(response.usage.model_dump_json(indent=2))

            raw_content = response.choices[0].message.content or "{}"

            try:
                json_content = json.loads(normalize_json_output(raw_content))
            except json.JSONDecodeError:
                self._logger.warning(
                    f"Invalid JSON returned by {self.model_name}:\n{raw_content})"
                )
                json_content = jsonfinder.only_json(raw_content)[2]
                self._logger.warning(
                    "Found JSON content within model response; continuing..."
                )

            try:
                content = self.schema.model_validate(json_content)

                assert response.usage

                # prompt_tokens_details might not be available in custom APIs
                cached_tokens = 0
                if (
                    hasattr(response.usage, "prompt_tokens_details")
                    and response.usage.prompt_tokens_details
                ):
                    cached_tokens = (
                        response.usage.prompt_tokens_details.cached_tokens or 0
                    )

                return SchematicGenerationResult(
                    content=content,
                    info=GenerationInfo(
                        schema_name=self.schema.__name__,
                        model=self.id,
                        duration=(t_end - t_start),
                        usage=UsageInfo(
                            input_tokens=response.usage.prompt_tokens,
                            output_tokens=response.usage.completion_tokens,
                            extra={"cached_input_tokens": cached_tokens},
                        ),
                    ),
                )

            except ValidationError as e:
                self._logger.error(
                    f"Error: {e.json(indent=2)}\nJSON content returned by {self.model_name} does not match expected schema:\n{raw_content}"
                )
                raise


class CustomGPT_4o(CustomOpenAISchematicGenerator[T]):
    def __init__(
        self,
        logger: Logger,
        base_url: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        super().__init__(
            model_name=model_name or settings.ntqai_model,
            logger=logger,
            base_url=base_url or settings.ntqai_base_url,
            api_key=api_key or settings.ntqai_api_key,
        )

    @property
    @override
    def max_tokens(self) -> int:
        return 128 * 1024


class CustomOpenAIEmbedder(Embedder):
    supported_arguments = ["dimensions"]

    def __init__(
        self,
        model_name: str,
        logger: Logger,
        base_url: str,
        api_key: str,
    ) -> None:
        self.model_name = model_name

        self._logger = logger
        self._base_url = base_url
        self._api_key = api_key

        self._client = AsyncClient(
            api_key=api_key,
            base_url=base_url,
        )
        self._tokenizer = CustomOpenAIEstimatingTokenizer(model_name=self.model_name)

    @property
    @override
    def id(self) -> str:
        return f"ntqai/{self.model_name}"

    @property
    @override
    def tokenizer(self) -> CustomOpenAIEstimatingTokenizer:
        return self._tokenizer

    @policy(
        [
            retry(
                exceptions=(
                    APIConnectionError,
                    APITimeoutError,
                    ConflictError,
                    RateLimitError,
                    APIResponseValidationError,
                ),
            ),
            retry(InternalServerError, max_exceptions=2, wait_times=(1.0, 5.0)),
        ]
    )
    @override
    async def embed(
        self,
        texts: list[str],
        hints: Mapping[str, Any] = {},
    ) -> EmbeddingResult:
        filtered_hints = {
            k: v for k, v in hints.items() if k in self.supported_arguments
        }
        try:
            response = await self._client.embeddings.create(
                model=self.model_name,
                input=texts,
                **filtered_hints,
            )
        except RateLimitError:
            self._logger.error(RATE_LIMIT_ERROR_MESSAGE)
            raise

        vectors = [data_point.embedding for data_point in response.data]
        return EmbeddingResult(vectors=vectors)


class CustomTextEmbedding(CustomOpenAIEmbedder):
    def __init__(
        self,
        logger: Logger,
        base_url: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        # Use settings as defaults if not provided
        super().__init__(
            model_name=model_name or settings.text_embedding_model,
            logger=logger,
            base_url=base_url or settings.text_embedding_url,
            api_key=api_key or settings.text_embedding_api_key,
        )

    @property
    @override
    def max_tokens(self) -> int:
        return 8192

    @property
    def dimensions(self) -> int:
        return settings.embedding_dimensions


class CustomModerationService(ModerationService):
    """Dummy moderation service that doesn't flag anything."""

    def __init__(self, logger: Logger) -> None:
        self._logger = logger

    @override
    async def check(self, content: str) -> ModerationCheck:
        # Return a check that doesn't flag anything
        return ModerationCheck(
            flagged=False,
            tags=[],
        )


class CustomOpenAIService(NLPService):
    @staticmethod
    def verify_environment() -> str | None:
        """Returns an error message if the environment is not set up correctly."""

        if not settings.ntqai_base_url:
            return """\
You're using the Custom OpenAI NLP service, but ntqai_base_url is not set.
Please set ntqai_base_url in your settings before running.
"""

        if not settings.ntqai_api_key:
            return """\
You're using the Custom OpenAI NLP service, but ntqai_api_key is not set.
Please set ntqai_api_key in your settings before running.
"""

        if not settings.text_embedding_url:
            return """\
You're using the Custom OpenAI NLP service, but text_embedding_url is not set.
Please set text_embedding_url in your settings before running.
"""

        if not settings.text_embedding_api_key:
            return """\
You're using the Custom OpenAI NLP service, but text_embedding_api_key is not set.
Please set text_embedding_api_key in your settings before running.
"""

        return None

    def __init__(
        self,
        logger: Logger,
    ) -> None:
        self._logger = logger

        self._logger.info(
            f"Initialized CustomOpenAIService with generator endpoint: {settings.ntqai_base_url}, "
            f"model: {settings.ntqai_model}, embedder endpoint: {settings.text_embedding_url}, "
            f"embedder model: {settings.text_embedding_model}"
        )

    @override
    async def get_schematic_generator(
        self, t: type[T]
    ) -> CustomOpenAISchematicGenerator[T]:
        # Use the same model for all schema types
        generator = CustomGPT_4o[t](
            logger=self._logger,
        )
        return generator  # type: ignore

    @override
    async def get_embedder(self) -> Embedder:
        return CustomTextEmbedding(
            logger=self._logger,
        )

    @override
    async def get_moderation_service(self) -> ModerationService:
        return CustomModerationService(self._logger)
