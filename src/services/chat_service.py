from typing import List, Dict
from src.agents.chat_agent import ChatAgent
from src.models.chat import ChatRequest
from src.utils.decorators import singleton
from src.config.settings import settings
from src.models.chat import WebSearchConfig
from src.models.chat import SearchProvider
from src.agents.researcher.main_agent import MainAgent, AgentInputState
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from src.services.conversation_service import ConversationService
import tiktoken
from fastapi import HTTPException
from src.common.types import Message
from src.services.utils import get_message_id


@singleton
class ChatService:
    def __init__(self):
        self.chat_agent = ChatAgent()
        self.conv_service = ConversationService()
        self.tokenizer = tiktoken.encoding_for_model("gpt-4o")

    def _format_history(self, history: List[Dict[str, str]]) -> List[BaseMessage]:
        """Converts simple dict history to LangChain message objects."""
        return [
            HumanMessage(content=item.get("content", ""))
            if item.get("role") == "user"
            else AIMessage(content=item.get("content", ""))
            for item in history
            if item.get("role") in ("user", "assistant")
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

    async def sanitize_message(self, message: Message):
        """Sanitize the message"""
        conversation_id = message.metadata.get("conversation_id")
        try:
            messages = await self.conv_service._list_messages(conversation_id)
            if messages:
                last_message_id = get_message_id(messages[-1])
                if last_message_id:
                    message.metadata.update({"last_message_id": last_message_id})
            else:
                raise HTTPException(status_code=404, detail="Conversation not found")
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error sanitizing message: {e}"
            )
        return message

    async def ask(self, request: ChatRequest):
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

        request.message = await self.sanitize_message(request.message)

        if request.agentic:
            main_agent = MainAgent(kb_id=request.message.metadata.get("kb_id"))
            initial_state: AgentInputState = {
                "messages": request.message,
                "web_search": web_search_config,
            }
            response = main_agent.generate_response(initial_state)
        else:
            response = await self.chat_agent.ask_normal(request, web_search_config)
        return response

    async def ask_sse(self, request: ChatRequest):
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
        if request.agentic:
            main_agent = MainAgent(kb_id=request.message.metadata.get("kb_id"))
            initial_state: AgentInputState = {
                "messages": request.message,
                "web_search": web_search_config,
            }
            response = main_agent.generate_streaming_response(initial_state)
        else:
            response = self.chat_agent.ask_stream(request, web_search_config)
        return response


def _get_api_key_for_provider(provider: SearchProvider) -> str:
    """Get API key based on the selected provider."""
    if provider == SearchProvider.TAVILY:
        return settings.tavily_api_key
    elif provider == SearchProvider.FIRECRAWL:
        return settings.firecrawl_api_key
