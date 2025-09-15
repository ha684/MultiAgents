from typing import List, Dict
from src.agents.chat_agent import ChatAgent
from src.models.chat import ChatRequest
from src.utils.decorators import singleton
from src.utils import format_history
from src.config.settings import settings
from src.models.chat import WebSearchConfig
from src.models.chat import SearchProvider
from src.agents.researcher.main_agent import MainAgent, AgentInputState
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from src.services.conversation_service import ConversationService
import tiktoken
from fastapi import HTTPException


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

    async def ask(self, request: ChatRequest):
        """Process a chat request and return a response."""
        if settings.enable_websearch and request.web_search:
            web_search_config = WebSearchConfig(
                provider=settings.websearch_provider,
                active=True,
                api_key=_get_api_key_for_provider(settings.websearch_provider),
            )
        else:
            web_search_config = WebSearchConfig(active=False)

        stream = getattr(request, "stream", False)
        request.messages = await self.messages_handling(request)

        if request.agentic:
            main_agent = MainAgent(kb_id=request.knowledge_base_id)
            initial_state: AgentInputState = {
                "messages": request.messages,
                "web_search": web_search_config,
            }

            if stream:
                response = main_agent.generate_streaming_response(initial_state)
            else:
                response = main_agent.generate_response(initial_state)
        else:
            if stream:
                response = self.chat_agent.ask_stream(request, web_search_config)
            else:
                response = await self.chat_agent.ask_normal(request, web_search_config)

        return response

    async def messages_handling(self, request: ChatRequest) -> List[BaseMessage]:
        """Handle messages for the chat request."""
        messages = await self.conv_service._list_messages(str(request.conversation_id))
        if not messages:
            raise HTTPException(status_code=404, detail="Conversation not found")

        dict_history = [item.model_dump() for item in request.messages[-5:]]
        messages = format_history(dict_history)
        return messages


def _get_api_key_for_provider(provider: SearchProvider) -> str:
    """Get API key based on the selected provider."""
    if provider == SearchProvider.TAVILY:
        return settings.tavily_api_key
    elif provider == SearchProvider.FIRECRAWL:
        return settings.firecrawl_api_key
