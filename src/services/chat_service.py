from typing import List, Dict, AsyncGenerator, Tuple
from src.agents.chat_agent import ChatAgent
from src.models.chat import ChatRequest
from src.utils.decorators import singleton
from src.config.settings import settings
from src.models.chat import WebSearchConfig
from src.models.chat import SearchProvider
from src.agents.researcher.main_agent import MainAgent, AgentInputState
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from src.services.conversation_service import ConversationService
from src.agents.summary_agent import SummaryAgent
from fastapi import HTTPException
from src.common.types import Message
from src.services.utils import get_message_id
from src.utils.logger_conf import logger


@singleton
class ChatService:
    def __init__(self):
        self.chat_agent = ChatAgent()
        self.conv_service = ConversationService()
        self.summary_agent = SummaryAgent()

    def _format_history(self, history: List[Message]) -> List[BaseMessage]:
        """Converts simple dict history to LangChain message objects."""
        return [
            HumanMessage(content=item.parts[0].text)
            if item.role == "user"
            else AIMessage(content=item.parts[0].text)
            for item in history
            if item.role in ("user", "agent")
        ]

    def sanitize_request(self, request: ChatRequest):
        """Sanitize the request"""
        if not request.message.metadata:
            raise HTTPException(status_code=400, detail="Metadata is required")

        required_fields = [
            "conversation_id",
            "kb_id",
            "user_id",
            "app_name",
        ]

        metadata = request.message.metadata
        for field_name in required_fields:
            if not metadata.get(field_name):
                raise HTTPException(status_code=400, detail=f"{field_name} is required")

        return request

    async def _manage_conversation_length(
        self, conversation: List[BaseMessage]
    ) -> List[BaseMessage]:
        """Manage conversation length using token counting and summarization."""
        min_messages_to_keep = 4
        max_conversation_tokens = 8192
        if len(conversation) <= min_messages_to_keep:
            return conversation
        total_tokens = self.summary_agent.count_tokens(conversation)

        if total_tokens <= max_conversation_tokens:
            return conversation

        if total_tokens > max_conversation_tokens:
            messages_to_keep = max(min_messages_to_keep, len(conversation) // 3)
            recent_messages = conversation[-messages_to_keep:]

            messages_to_summarize = conversation[:-messages_to_keep]

            if messages_to_summarize:
                try:
                    summary = await self.summary_agent.summarize_conversation(
                        messages_to_summarize
                    )

                    if recent_messages and isinstance(
                        recent_messages[-1], HumanMessage
                    ):
                        recent_messages[-1] = (
                            self.summary_agent.append_summary_to_user_message(
                                recent_messages[-1], summary
                            )
                        )

                    return recent_messages
                except Exception as e:
                    logger.warning(f"Failed to summarize conversation: {e}")
                    return recent_messages
        return conversation

    async def sanitize_message(self, message: Message) -> List[BaseMessage]:
        """Sanitize the message and manage conversation length."""
        conversation_id = message.metadata.get("conversation_id")
        try:
            conversation_history = await self.conv_service._list_messages(
                conversation_id
            )
            if conversation_history:
                last_message_id = get_message_id(conversation_history[-1])
                if last_message_id:
                    message.metadata.update({"last_message_id": last_message_id})

            await self.conv_service.add_message(message, conversation_id)
            conversation_history.append(message)

            formatted_conversation = self._format_history(conversation_history)

            managed_conversation = await self._manage_conversation_length(
                formatted_conversation
            )

            original_tokens = self.summary_agent.count_tokens(formatted_conversation)
            managed_tokens = self.summary_agent.count_tokens(managed_conversation)

            if original_tokens != managed_tokens:
                logger.info(
                    f"Conversation length managed: {original_tokens} → {managed_tokens} tokens "
                    f"({len(formatted_conversation)} → {len(managed_conversation)} messages)"
                )

            return managed_conversation

        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error sanitizing message: {e}"
            )

    async def ask(self, request: ChatRequest) -> Tuple[Message, List[Dict]]:
        """Process a chat request and return a response."""
        request = self.sanitize_request(request)
        if settings.enable_websearch and request.web_search:
            web_search_config = WebSearchConfig(
                provider=settings.websearch_provider,
                active=True,
                api_key=_get_api_key_for_provider(settings.websearch_provider),
            )
        else:
            web_search_config = WebSearchConfig(active=False)

        metadata = request.message.metadata
        conversation = await self.sanitize_message(request.message)

        if request.agentic:
            main_agent = MainAgent(kb_id=metadata.get("kb_id"))
            initial_state: AgentInputState = {
                "messages": conversation,
                "web_search": web_search_config,
            }
            response = main_agent.generate_response(initial_state)
        else:
            response, sources = await self.chat_agent.ask_normal(
                conversation, web_search_config, metadata
            )
        return response, sources

    async def ask_sse(
        self, request: ChatRequest
    ) -> AsyncGenerator[str | BaseMessage, None]:
        """Process a chat request and return a streaming response."""
        request = self.sanitize_request(request)
        if settings.enable_websearch and request.web_search:
            web_search_config = WebSearchConfig(
                provider=settings.websearch_provider,
                active=True,
                api_key=_get_api_key_for_provider(settings.websearch_provider),
            )
        else:
            web_search_config = WebSearchConfig(active=False)

        metadata = request.message.metadata
        conversation = await self.sanitize_message(request.message)

        if request.agentic:
            main_agent = MainAgent(kb_id=metadata.get("kb_id"))
            initial_state: AgentInputState = {
                "messages": conversation,
                "web_search": web_search_config,
            }
            response = main_agent.generate_streaming_response(initial_state)
        else:
            response = self.chat_agent.ask_stream(
                conversation, web_search_config, metadata
            )
        return response


def _get_api_key_for_provider(provider: SearchProvider) -> str:
    """Get API key based on the selected provider."""
    if provider == SearchProvider.TAVILY:
        return settings.tavily_api_key
    elif provider == SearchProvider.FIRECRAWL:
        return settings.firecrawl_api_key
