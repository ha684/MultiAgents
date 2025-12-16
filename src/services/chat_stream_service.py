# src/services/chat_stream_service.py
"""
Chat Streaming Service

This service manages WebSocket connections for real-time chat streaming:
- Handles client connections and disconnections
- Replays events for late subscribers or reconnecting clients
- Processes client commands (stop, ping, resume)
- Streams events from Redis to WebSocket
"""

import asyncio
import uuid
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from src.domain.schemas.chat_task import (
    ChatTaskStatus,
    WSCommand,
    WSCommandType,
    WSEvent,
    WSEventType,
)
from src.infrastructure.tasks import chat_stream_buffer, task_client
from src.infrastructure.tasks.stream_buffer import StreamMessage
from src.utils.decorators import singleton
from src.utils.logger_conf import logger


class ChatWebSocketManager:
    """
    Manages a single WebSocket connection for chat streaming.

    Features:
    - Replay from beginning for late subscribers
    - Resume from last_event_id for reconnecting clients
    - Command handling (stop, ping)
    - Graceful disconnection
    """

    def __init__(self, websocket: WebSocket, task_id: str):
        self.websocket = websocket
        self.task_id = task_id
        self.is_connected = False
        self.last_event_id: str | None = None

    async def connect(self) -> bool:
        """Accept WebSocket connection"""
        try:
            await self.websocket.accept()
            self.is_connected = True
            logger.info(f"WebSocket connected for task: {self.task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to accept WebSocket for task {self.task_id}: {e}")
            return False

    async def disconnect(self) -> None:
        """Close WebSocket connection gracefully"""
        self.is_connected = False
        try:
            await self.websocket.close()
        except Exception as e:
            logger.debug(f"Error closing WebSocket for task {self.task_id}: {e}")
        logger.info(f"WebSocket disconnected for task: {self.task_id}")

    async def send_event(self, event: WSEvent) -> bool:
        """Send event to client"""
        if not self.is_connected:
            return False

        try:
            await self.websocket.send_json(event.to_json())
            return True
        except Exception as e:
            logger.error(f"Failed to send event to WebSocket {self.task_id}: {e}")
            self.is_connected = False
            return False

    async def send_stream_message(self, message: StreamMessage) -> bool:
        """Convert StreamMessage to WSEvent and send"""
        event_type_map = {
            "message_start": WSEventType.MESSAGE_START,
            "content_block_delta": WSEventType.CONTENT_DELTA,
            "status": WSEventType.STATUS,
            "message_stop": WSEventType.MESSAGE_STOP,
            "error": WSEventType.ERROR,
        }

        ws_type = event_type_map.get(message.event_type, WSEventType.STATUS)

        event = WSEvent(
            type=ws_type,
            event_id=message.event_id,
            data=message.data,
        )

        success = await self.send_event(event)
        if success:
            self.last_event_id = message.event_id
        return success

    async def send_connected_event(self, task_status: str | None = None) -> bool:
        """Send initial connected event"""
        event = WSEvent(
            type=WSEventType.CONNECTED,
            data={
                "task_id": self.task_id,
                "status": task_status or "unknown",
                "message": "Connected to chat stream",
            },
        )
        return await self.send_event(event)

    async def replay_events(self, from_event_id: str | None = None) -> int:
        """
        Replay events from Redis stream.

        Args:
            from_event_id: Start replaying after this event ID (exclusive)

        Returns:
            Number of events replayed
        """
        try:
            if from_event_id:
                messages = await chat_stream_buffer.read_events_from(
                    self.task_id, from_event_id
                )
            else:
                messages = await chat_stream_buffer.read_all_events(self.task_id)

            count = 0
            for message in messages:
                if not self.is_connected:
                    break
                if await self.send_stream_message(message):
                    count += 1

            logger.info(f"Replayed {count} events for task {self.task_id}")
            return count

        except Exception as e:
            logger.error(f"Failed to replay events for task {self.task_id}: {e}")
            return 0

    async def handle_command(self, data: dict[str, Any]) -> bool:
        """
        Handle command from client.

        Returns:
            False if connection should be closed
        """
        try:
            command = WSCommand(**data)

            if command.action == WSCommandType.STOP:
                logger.info(f"Stop command received for task {self.task_id}")
                await chat_stream_buffer.request_cancellation(self.task_id)
                await self.send_event(
                    WSEvent(
                        type=WSEventType.CANCELLED,
                        data={"message": "Task cancellation requested"},
                    )
                )
                return False

            elif command.action == WSCommandType.PING:
                await self.send_event(
                    WSEvent(
                        type=WSEventType.PING,
                        data={"message": "pong"},
                    )
                )
                return True

            elif command.action == WSCommandType.RESUME:
                # Client wants to resume from a specific event
                if command.last_event_id:
                    await self.replay_events(command.last_event_id)
                return True

            return True

        except Exception as e:
            logger.error(f"Error handling command for task {self.task_id}: {e}")
            await self.send_event(
                WSEvent(
                    type=WSEventType.ERROR,
                    data={"type": "command_error", "message": str(e)},
                )
            )
            return True

    async def listen_for_commands(self) -> None:
        """Listen for commands from client"""
        try:
            while self.is_connected:
                try:
                    # Use receive_json with timeout
                    data = await asyncio.wait_for(
                        self.websocket.receive_json(),
                        timeout=30.0,
                    )
                    should_continue = await self.handle_command(data)
                    if not should_continue:
                        break
                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    continue
                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected by client: {self.task_id}")
                    break
        except Exception as e:
            logger.error(f"Error in command listener for task {self.task_id}: {e}")
        finally:
            self.is_connected = False

    async def stream_events(self, from_event_id: str | None = None) -> None:
        """
        Stream events to client.

        This method:
        1. Replays any missed events
        2. Subscribes to real-time events
        3. Exits when task completes or client disconnects
        """
        try:
            # Get current task status
            status = await chat_stream_buffer.get_status(self.task_id)
            await self.send_connected_event(status.value if status else None)

            # Check if task already completed
            if status in (
                ChatTaskStatus.COMPLETE,
                ChatTaskStatus.CANCELLED,
                ChatTaskStatus.ERROR,
            ):
                # Just replay all events
                await self.replay_events(from_event_id)
                logger.info(f"Task {self.task_id} already completed, replayed events")
                return

            # Subscribe and stream
            async for message in chat_stream_buffer.subscribe_to_stream(
                self.task_id,
                last_event_id=from_event_id,
            ):
                if not self.is_connected:
                    break

                await self.send_stream_message(message)

                # Check for completion
                if message.event_type in ("message_stop", "error"):
                    break

        except Exception as e:
            logger.error(f"Error streaming events for task {self.task_id}: {e}")
            await self.send_event(
                WSEvent(
                    type=WSEventType.ERROR,
                    data={"type": "stream_error", "message": str(e)},
                )
            )


@singleton
class ChatStreamService:
    """
    Service for managing chat streaming via WebSocket.

    Usage:
    1. Client creates a chat task via POST /chat/ask/task
    2. Client connects to WebSocket /chat/stream/{task_id}
    3. Server streams events in real-time
    4. Client can send commands (stop, ping)
    """

    async def handle_websocket(
        self,
        websocket: WebSocket,
        task_id: str,
        last_event_id: str | None = None,
    ) -> None:
        """
        Main WebSocket handler.

        Args:
            websocket: FastAPI WebSocket connection
            task_id: The chat task ID to stream
            last_event_id: Optional event ID to resume from
        """
        manager = ChatWebSocketManager(websocket, task_id)

        if not await manager.connect():
            return

        try:
            # Verify task exists (check if status or stream exists in Redis)
            status = await chat_stream_buffer.get_status(task_id)
            if status is None:
                await manager.send_event(
                    WSEvent(
                        type=WSEventType.ERROR,
                        data={
                            "type": "task_not_found",
                            "message": f"Task {task_id} not found or already completed",
                        },
                    )
                )
                return

            # Run streaming and command listening concurrently
            stream_task = asyncio.create_task(manager.stream_events(last_event_id))
            command_task = asyncio.create_task(manager.listen_for_commands())

            # Wait for either to complete
            done, pending = await asyncio.wait(
                [stream_task, command_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        except WebSocketDisconnect:
            logger.info(f"Client disconnected from task {task_id}")
        except Exception as e:
            logger.error(f"Error in WebSocket handler for task {task_id}: {e}")
        finally:
            await manager.disconnect()

    async def create_chat_task(
        self,
        conversation_id: uuid.UUID,
        user_id: str,
        kb_id: uuid.UUID,
        message_text: str,
        message_metadata: dict[str, Any],
        agentic: bool = False,
        web_search: bool = False,
    ) -> str | None:
        """
        Create a new chat task and queue it for processing.

        Returns:
            Task ID if successful, None otherwise
        """
        # Generate task ID
        task_id = str(uuid.uuid4())

        # Initialize task in Redis
        await chat_stream_buffer.init_task(
            task_id=task_id,
            conversation_id=str(conversation_id),
            user_id=user_id,
            kb_id=str(kb_id),
            metadata={"agentic": agentic, "web_search": web_search},
        )

        # Queue Celery task
        queued_task_id = task_client.queue_chat_inference(
            task_id=task_id,
            conversation_id=conversation_id,
            user_id=user_id,
            kb_id=kb_id,
            message_text=message_text,
            message_metadata=message_metadata,
            agentic=agentic,
            web_search_active=web_search,
        )

        if queued_task_id:
            logger.info(f"Created chat task: {task_id}")
            return task_id
        else:
            # Cleanup on failure
            await chat_stream_buffer.cleanup_task(task_id)
            logger.error(f"Failed to queue chat task: {task_id}")
            return None

    async def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        """Get the status of a chat task"""
        status = await chat_stream_buffer.get_status(task_id)
        if status is None:
            return None

        metadata = await chat_stream_buffer.get_metadata(task_id)

        return {
            "task_id": task_id,
            "status": status.value,
            "metadata": metadata,
        }

    async def cancel_task(self, task_id: str) -> bool:
        """Request cancellation of a chat task"""
        return await chat_stream_buffer.request_cancellation(task_id)


# Singleton instance
chat_stream_service = ChatStreamService()
