from typing import List, Dict, AsyncGenerator, Union, Any
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import BaseMessage
from src.config.llm_config import SupportedLLMProviders
from src.llm.factory import get_llm
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from pydantic import BaseModel, Field
from src.nlp.language_detector import language_detection
from src.prompts.get_prompt_template import load_prompt_template
from src.utils.logger_conf import logger
from src.utils.decorators import singleton


class CitedAnswer(BaseModel):
    """Answer the user question based only on the given sources, and cite the sources used."""

    answer: str = Field(
        ...,
        description="The answer to the user question, which is based only on the given sources.",
    )
    citations: List[int] = Field(
        ...,
        description="The integer IDs of the SPECIFIC sources which justify the answer.",
    )


@singleton
class ResponseAgent:
    """Agent responsible for generating the final response based on verified context, citations, and history."""

    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        logger.info("Response Agent initialized successfully.")
        self.llm = get_llm(provider)

    def _get_language_and_prompts(self, query: str):
        """Detect language and load appropriate prompts."""
        # Detect language
        detected_language, confidence = language_detection(query, type="query")

        # Map language codes to supported languages
        language_map = {"vi": "vi", "ja": "ja", "ko": "ko", "en": "en"}

        # Default to English if language not supported or confidence is low
        language_code = language_map.get(detected_language, "en")

        logger.info(
            f"Detected language: {detected_language} (confidence: {confidence}), using: {language_code}"
        )

        try:
            # Load response prompt
            response_prompt_template = load_prompt_template(
                task_name="response_generation", language_code=language_code
            )

            # Load no answer prompt
            no_answer_prompt_template = load_prompt_template(
                task_name="no_answer_response", language_code=language_code
            )

            return response_prompt_template, no_answer_prompt_template, language_code

        except Exception as e:
            logger.exception(f"Error loading prompts for language {language_code}: {e}")
            # Fallback to English
            response_prompt_template = load_prompt_template(
                task_name="response_generation", language_code="en"
            )
            no_answer_prompt_template = load_prompt_template(
                task_name="no_answer_response", language_code="en"
            )
            return response_prompt_template, no_answer_prompt_template, "en"

    def _format_context_for_response(self, documents: List[Document]) -> str:
        """Formats documents for the response prompt."""
        if not documents:
            return "<documents>No relevant documents found.</documents>"

        xml_output = "<documents>\n"

        if not documents:
            return "<documents>No relevant documents found.</documents>"

        xml_output = "<documents>\n"

        for i, doc in enumerate(documents):
            xml_output += f'  <document index="{i + 1}">\n'
            metadata = getattr(doc, "metadata", {})
            source = metadata.get("original_filename", f"Document {i + 1}")
            folder_path = metadata.get("folder_path", "")
            sheet_name = metadata.get("sheet_name", "")
            sheet_name = metadata.get("sheet_name", "")
            xml_output += f"<source>{source}</source>\n"
            if folder_path:
                xml_output += f"<folder_path>{folder_path}</folder_path>\n"
            if sheet_name:
                xml_output += f"<sheet_name>{sheet_name}</sheet_name>\n"
            if sheet_name:
                xml_output += f"<sheet_name>{sheet_name}</sheet_name>\n"
            content = getattr(doc, "page_content", "")
            xml_output += "<document_content>\n"
            xml_output += f"{content}\n"
            xml_output += "</document_content>\n"
            xml_output += "</document>\n"
        xml_output += "</documents>"

        return xml_output

    def _prepare_messages(
        self, contexts: List[Document], history: List[BaseMessage]
    ) -> ChatPromptTemplate:
        """Prepare messages for both streaming and non-streaming responses."""
        current_query = history[-1].content

        response_prompt_template, no_answer_prompt_template, language_code = (
            self._get_language_and_prompts(current_query)
        )

        if contexts:
            logger.info(
                f'Response Agent: Preparing response for query: "{current_query}" with {len(contexts)} contexts.'
            )
            formatted_context = self._format_context_for_response(contexts)
            system_message = SystemMessage(content=response_prompt_template)
            new_query = HumanMessage(
                content=f"{formatted_context}\n---\n{current_query}"
            )
            messages = [system_message] + history[:-1] + [new_query]
        else:
            logger.warning(
                f"Response Agent: Preparing 'information not found' response in {language_code}."
            )
            system_message = SystemMessage(content=no_answer_prompt_template)
            new_query = HumanMessage(
                content=f"User query: {current_query}\n\nRemember this is the case that no document found."
            )
            messages = [system_message] + history[:-1] + [new_query]

        messages_prompt = ChatPromptTemplate.from_messages(messages)
        return messages_prompt

    async def generate_response(
        self,
        contexts: List[Document],
        history: List[BaseMessage],
    ) -> AIMessage:
        """Generates a full response (non-streaming) based on verification results and history."""
        try:
            messages_prompt = self._prepare_messages(contexts, history)
            response_chain = messages_prompt | self.llm
            response = await response_chain.ainvoke({})
            logger.info(f"Response type: {type(response)}")
            return response

        except Exception as e:
            logger.exception(f"Error during response generation: {e}")
            raise e

    async def generate_streaming_response(
        self,
        contexts: List[Document],
        history: List[BaseMessage],
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        """Streams response content chunks and final complete message from the LLM."""
        try:
            messages_prompt = self._prepare_messages(contexts, history)
            response_chain = messages_prompt | self.llm

            accumulated_content = ""
            run_id = None
            response_metadata = {}
            formatted_messages = messages_prompt.format_messages()

            async for chunk in response_chain.astream({}):
                if hasattr(chunk, "content") and chunk.content:
                    accumulated_content += chunk.content
                    yield chunk.content

                if hasattr(chunk, "id") and chunk.id:
                    run_id = chunk.id

                if hasattr(chunk, "response_metadata") and chunk.response_metadata:
                    response_metadata.update(chunk.response_metadata)

            if accumulated_content:
                usage_data = calculate_usage_metadata(
                    formatted_messages, accumulated_content
                )
                response_metadata.update(usage_data)
                final_response = {
                    "content": accumulated_content,
                    "response_metadata": response_metadata,
                    "type": "ai",
                    "name": None,
                    "id": run_id or "unknown",
                    "example": False,
                    "tool_calls": [],
                    "invalid_tool_calls": [],
                }

                yield final_response

        except Exception as e:
            logger.exception(f"Error during streaming response generation: {e}")
            yield "error"


def count_tokens(text: str) -> int:
    """Count tokens in text using the same tokenizer as the chat agent."""
    return len(text) // 4


def calculate_usage_metadata(
    prompt_messages: List[BaseMessage], response_content: str
) -> Dict[str, Any]:
    """Calculate usage metadata by counting tokens in prompt and response."""
    try:
        input_text = ""
        for msg in prompt_messages:
            if hasattr(msg, "content"):
                input_text += msg.content + " "

        input_tokens = count_tokens(input_text)
        output_tokens = count_tokens(response_content)
        total_tokens = input_tokens + output_tokens

        return {
            "token_usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": total_tokens,
                "prompt_tokens_details": {},
                "completion_tokens_details": {},
            },
        }
    except Exception as e:
        logger.warning(f"Failed to calculate usage metadata: {e}")
        return {
            "token_usage": {
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "prompt_tokens_details": {},
                "completion_tokens_details": {},
            },
        }
