from fastapi import HTTPException
from typing import List, Dict, Any
from src.agents.chat_agent import ChatAgent
from src.models.chat import ChatRequest
from src.models.reference import Reference
from src.utils.reference import normalize_ref
from langchain_core.documents import Document
from src.utils.logger_conf import logger
from src.utils.decorators import singleton_per_key
from src.agents.researcher.main_agent import MainAgent
from src.utils import format_history
import uuid


@singleton_per_key(lambda kb_id, config: (kb_id, tuple(sorted(config.items()))))
class ChatService:
    def __init__(self, kb_id: uuid.UUID, config: Dict[str, Any]):
        self.chat_agent = ChatAgent()
        self.langgraph_agent = MainAgent(kb_id=kb_id, config=config)
        self.config = config

    async def ask(self, request: ChatRequest):
        """Process a chat request and return a response."""
        if not request.messages:
            raise HTTPException(status_code=400, detail="Messages are required")
        request.messages = request.messages[-5:]
        request.messages = format_history(request.messages)
        try:
            if request.agentic:
                response = await self._ask_langgraph(request)
            else:
                response = await self._ask_original(request)
            return response

        except Exception as e:
            logger.exception(f"Error processing chat request: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error creating message: {str(e)}"
            )

    async def _ask_langgraph(self, request: ChatRequest):
        """Process request using LangGraph and formats the output for the API."""
        try:
            if not request.stream:
                final_state = await self.langgraph_agent.generate_response(request)
                return final_state
            else:
                return await self.langgraph_agent.generate_streaming_response(request)
        except Exception as e:
            logger.exception(f"Error processing chat request: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error creating message: {str(e)}"
            )

    async def _ask_original(self, request: ChatRequest):
        """Process request using original chat agent"""
        if not request.stream:
            return await self.chat_agent.ask_normal(request=request)
        else:
            return await self.chat_agent.ask_stream(request=request)

    def create_reference(self, retrieved_docs: List[Document]) -> List[Dict]:
        references = []
        formated_docs = normalize_ref(retrieved_docs)

        for i, doc in enumerate(formated_docs):
            reference = Reference(
                source_id=str(doc.metadata.get("_id")),
                source_index=i,
                source=str(doc.metadata.get("original_filename")),
                quote="",
                page_content=doc.page_content,
            )
            references.append(reference.model_dump())

        return references
