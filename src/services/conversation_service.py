import base64
import os
import uuid
from src.common.types import FileContent, FilePart, Message
from fastapi import Response
from .types import (
    CreateConversationResponse,
    GetEventResponse,
    ListAgentResponse,
    ListConversationResponse,
    ListMessageResponse,
    ListTaskResponse,
    MessageInfo,
    PendingMessageResponse,
    RegisterAgentResponse,
    SendMessageResponse,
)
from .server.adk_host_manager import ADKHostManager, get_message_id
from typing import Optional, AsyncGenerator
import json
from src.utils.logger_conf import logger
from src.utils.decorators import singleton

@singleton
class ConversationServer:
    """ConversationServer is the backend to serve the agent interactions"""

    def __init__(self):
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        uses_vertex_ai = (
            os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE"
        )
        db_url = os.environ.get("SYNC_DATABASE_URL", "")

        self.manager = ADKHostManager(
            api_key=api_key, uses_vertex_ai=uses_vertex_ai, db_url=db_url
        )

        logger.info("ADK Host Manager initialized")

        self._file_cache = {}
        self._message_to_cache = {}

    async def update_api_key(
        self,
        api_key: str,
        app_name: str,
    ) -> str:
        if isinstance(self.manager, ADKHostManager):
            return await self.manager.update_api_key(api_key, app_name)

    async def _initialize_host(
        self,
        app_name: str,
    ) -> str:
        return await self.manager._initialize_host(app_name)

    async def _create_conversation(
        self, app_name: str, user_id: str
    ) -> CreateConversationResponse:
        c = await self.manager.create_conversation(app_name, user_id)
        return CreateConversationResponse(result=c)

    async def _send_message(self, message: Message) -> SendMessageResponse:
        try:
            message = await self.manager.sanitize_message(message)
            response_data = None
            async for result in self.manager.process_message(message, stream=False):
                if result.get("type") == "final_result":
                    response_data = result.get("response")
                    break

            if response_data is None:
                raise Exception("No final result received from process_message")

            return SendMessageResponse(
                result=MessageInfo(
                    conversation_id=message.metadata["conversation_id"],
                    message_id=message.metadata["message_id"],
                    context_id=message.metadata["context_id"],
                    response=response_data,
                )
            )
        except Exception as e:
            raise e

    async def _send_message_stream(self, message: Message) -> AsyncGenerator[str, None]:
        """Stream message processing results"""
        try:
            message = await self.manager.sanitize_message(message)
            async for chunk in self.manager.process_message(message, stream=True):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

        except Exception as e:
            raise e

    async def _list_messages(self, conversation_id: str) -> ListMessageResponse:
        conversation = await self.manager.get_conversation(conversation_id)
        if conversation:
            messages = await self.manager.conv_repository.get_messages(conversation_id)
            return ListMessageResponse(result=self.cache_content(messages))
        return ListMessageResponse(result=[])

    def cache_content(self, messages: list[Message]):
        rval = []
        for m in messages:
            message_id = get_message_id(m)
            if not message_id:
                rval.append(m)
                continue
            new_parts = []
            for i, part in enumerate(m.parts):
                if part.type != "file":
                    new_parts.append(part)
                    continue
                message_part_id = f"{message_id}:{i}"
                if message_part_id in self._message_to_cache:
                    cache_id = self._message_to_cache[message_part_id]
                else:
                    cache_id = str(uuid.uuid4())
                    self._message_to_cache[message_part_id] = cache_id
                new_parts.append(
                    FilePart(
                        file=FileContent(
                            mimeType=part.file.mimeType,
                            uri=f"/message/file/{cache_id}",
                        )
                    )
                )
                if cache_id not in self._file_cache:
                    self._file_cache[cache_id] = part
            m.parts = new_parts
            rval.append(m)
        return rval

    async def _pending_messages(self) -> PendingMessageResponse:
        pending_messages = await self.manager.get_pending_messages()
        return PendingMessageResponse(result=pending_messages)

    async def _list_conversation(
        self, app_name: Optional[str], user_id: Optional[str]
    ) -> ListConversationResponse:
        result = await self.manager.list_conversations(app_name, user_id)
        return ListConversationResponse(result=result)

    async def _get_events_host_agent(
        self, conversation_id: Optional[str]
    ) -> GetEventResponse:
        result = await self.manager.get_events_host_agent(
            conversation_id=conversation_id
        )
        return GetEventResponse(result=result)

    async def _get_events_all(self, conversation_id: Optional[str]) -> GetEventResponse:
        result = await self.manager.get_events_all(conversation_id=conversation_id)
        return GetEventResponse(result=result)

    async def _list_tasks(self) -> ListTaskResponse:
        result = await self.manager.list_tasks()
        return ListTaskResponse(result=result)

    async def _register_agent(
        self,
        path: str,
        app_name: str,
    ) -> RegisterAgentResponse:
        result = await self.manager.register_agent(path, app_name)
        return RegisterAgentResponse(result=result)

    async def _list_agents(self) -> ListAgentResponse:
        return ListAgentResponse(result=self.manager.agents)

    async def _delete_conversation(self, conversation_id: str) -> str:
        """Delete a conversation and all related data"""
        result = await self.manager.delete_conversation(conversation_id)
        return f"Conversation {conversation_id} deleted successfully" if result else f"Conversation {conversation_id} not found"

    async def _files(self, file_id: str) -> Response:
        if file_id not in self._file_cache:
            raise Exception("file not found")
        part = self._file_cache[file_id]
        if "image" in part.file.mimeType:
            return Response(
                content=base64.b64decode(part.file.bytes),
                media_type=part.file.mimeType,
            )
        return Response(content=part.file.bytes, media_type=part.file.mimeType)
