import base64
import uuid
from typing import Optional
from fastapi import Response
from src.common.types import FileContent, FilePart, Message
from src.db.repository.conversation import ConversationRepository
from src.utils.decorators import singleton
from src.utils.logger_conf import logger
from src.services.server.adk_host_manager import get_message_id
from src.services.types import (
    CreateConversationResponse,
    GetEventResponse,
    ListConversationResponse,
    ListTaskResponse,
)


@singleton
class ConversationService:
    """ConversationService is the backend to serve the conversation management"""

    def __init__(self):
        self.conv_repository = ConversationRepository()
        logger.info("ConversationService initialized")
        self._file_cache = {}
        self._message_to_cache = {}

    async def _create_conversation(
        self, app_name: str, user_id: str
    ) -> CreateConversationResponse:
        c = await self.conv_repository.create_conversation(app_name, user_id)
        return CreateConversationResponse(result=c)

    async def _list_messages(self, conversation_id: str) -> list[Message]:
        conversation = await self.conv_repository.get_conversation(conversation_id)
        if conversation:
            messages = await self.conv_repository.get_messages(conversation_id)
            return self.cache_content(messages)
        return []

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

    async def _list_conversation(
        self, app_name: Optional[str], user_id: Optional[str]
    ) -> ListConversationResponse:
        result = await self.conv_repository.list_conversations(app_name, user_id)
        return ListConversationResponse(result=result)

    async def _get_events_all(self, conversation_id: Optional[str]) -> GetEventResponse:
        result = await self.conv_repository.get_events_all(
            conversation_id=conversation_id
        )
        return GetEventResponse(result=result)

    async def _list_tasks(self) -> ListTaskResponse:
        result = await self.conv_repository.list_tasks()
        return ListTaskResponse(result=result)

    async def _delete_conversation(self, conversation_id: str) -> str:
        """Delete a conversation and all related data"""
        result = await self.conv_repository.delete_conversation(conversation_id)
        return (
            f"Conversation {conversation_id} deleted successfully"
            if result
            else f"Conversation {conversation_id} not found"
        )

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
