from fastapi import HTTPException
from typing import List, Dict
from src.agents.chat_agent import ChatAgent
from src.models.chat import ChatRequest
from src.utils.logger_conf import logger
from src.utils.decorators import singleton
from src.utils import format_history
from src.config.settings import settings
from src.models.chat import WebSearchConfig
from src.models.chat import SearchProvider
from src.agents.researcher.main_agent import MainAgent, AgentInputState
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
@singleton
class ChatService:
    def __init__(self):
        self.chat_agent = ChatAgent()
        
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
        try:
            if settings.enable_websearch and request.web_search:
                web_search_config = WebSearchConfig(
                    provider=settings.websearch_provider,
                    active=True,
                    api_key=_get_api_key_for_provider(settings.websearch_provider),
                )
            else:
                web_search_config = WebSearchConfig(active=False)
                
            stream = getattr(request, "stream", False)
            
            if request.agentic:
                main_agent = MainAgent(kb_id=request.knowledge_base_id)
                dict_history = [item.model_dump() for item in request.messages[-5:]]
                messages = format_history(dict_history)
                initial_state: AgentInputState = {
                    "messages": messages,
                    "folder_context": request.folder_context,
                    "web_search": web_search_config,
                }

                if stream:
                    response = main_agent.generate_streaming_response(initial_state)
                else:
                    response = main_agent.generate_response(initial_state)
            else:
                dict_history = [item.model_dump() for item in request.messages[-5:]]
                lc_history = self._format_history(dict_history)
                request.messages = lc_history

                if stream:
                    response = self.chat_agent.ask_stream(request, web_search_config)
                else:
                    response = await self.chat_agent.ask_normal(request, web_search_config)

            return response

        except Exception as e:
            logger.exception(f"Error processing chat request: {str(e)}")
            raise HTTPException(status_code=500, detail=f"{str(e)}")


def _get_api_key_for_provider(provider: SearchProvider) -> str:
    """Get API key based on the selected provider."""
    if provider == SearchProvider.TAVILY:
        return settings.tavily_api_key
    elif provider == SearchProvider.FIRECRAWL:
        return settings.firecrawl_api_key

