# src/api/websocket.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.services.document_service import DocumentService
from src.event_pub import get_event_publisher
from src.utils.constants import DOCUMENT_STATUS_CHANNEL
import uuid
import asyncio
from typing import Dict, Any, Optional
from src.utils.logger_conf import logger

router = APIRouter(prefix="/websocket", tags=["WebSocket"])


class WebSocketManager:
    """Manages WebSocket connection for document status updates"""

    def __init__(self, websocket: WebSocket, document_id: uuid.UUID):
        self.websocket = websocket
        self.document_id = document_id
        self.document_service = DocumentService()
        self.is_connected = False

    async def connect(self) -> bool:
        """Establish WebSocket connection"""
        try:
            await self.websocket.accept()
            self.is_connected = True
            logger.info(
                f"WebSocket connection established for document: {self.document_id}"
            )
            return True
        except Exception as e:
            logger.error(
                f"Failed to establish WebSocket connection for document {self.document_id}: {e}"
            )
            return False

    async def send_message(
        self,
        message_type: str,
        data: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
    ) -> bool:
        """Send message to client with error handling"""
        if not self.is_connected:
            return False

        try:
            payload = {"type": message_type}
            if data is not None:
                payload["data"] = data
            if message is not None:
                payload["message"] = message

            await self.websocket.send_json(payload)
            return True
        except Exception as e:
            logger.error(
                f"Failed to send message to WebSocket for document {self.document_id}: {e}"
            )
            self.is_connected = False
            return False

    async def send_initial_status(self) -> bool:
        """Send initial document status to client"""
        try:
            initial_status = await self.document_service.get_document_status(
                self.document_id
            )
            status_data = initial_status.model_dump(mode="json")

            success = await self.send_message("initial_status", data=status_data)
            if success:
                logger.info(f"Sent initial status for document {self.document_id}")
            return success

        except Exception as e:
            logger.error(
                f"Failed to get initial status for document {self.document_id}: {e}"
            )
            await self.send_message(
                "error", message=f"Failed to get initial status: {str(e)}"
            )
            return False

    async def process_status_event(self, event: Dict[str, Any]) -> bool:
        """Process and send status update event"""
        try:
            event_doc_id = event.get("id") or event.get("document_id")
            if event_doc_id != str(self.document_id):
                return True
            success = await self.send_message("status_update", data=event)
            if not success:
                return False

            logger.info(
                f"Sent status update for document {self.document_id}: {event.get('status')}"
            )
            status = event.get("status")
            if status in ["COMPLETED", "FAILED"]:
                await self.send_message(
                    "complete", message=f"Processing finished with status: {status}"
                )
                logger.info(f"Processing complete for document {self.document_id}")
                return False

            return True

        except Exception as e:
            logger.error(f"Error processing event for document {self.document_id}: {e}")
            await self.send_message(
                "error", message=f"Error processing event: {str(e)}"
            )
            return False

    async def listen_for_updates(self) -> None:
        """Listen for status updates from event publisher"""
        event_publisher = await get_event_publisher()
        try:
            async for event in event_publisher.subscribe(DOCUMENT_STATUS_CHANNEL):
                if not self.is_connected:
                    break

                should_continue = await self.process_status_event(event)
                if not should_continue:
                    break

        except asyncio.CancelledError:
            logger.info(
                f"Status update listener cancelled for document {self.document_id}"
            )
        except Exception as e:
            logger.error(
                f"Error in status update listener for document {self.document_id}: {e}"
            )
            await self.send_message(
                "error", message=f"Error in update listener: {str(e)}"
            )
        finally:
            await event_publisher.disconnect()

    async def disconnect(self) -> None:
        """Clean up WebSocket connection"""
        self.is_connected = False
        try:
            await self.websocket.close()
        except Exception as e:
            logger.debug(
                f"Error closing WebSocket for document {self.document_id}: {e}"
            )

        logger.info(f"WebSocket connection closed for document {self.document_id}")


@router.websocket("/ws/document_status/{document_id}")
async def document_status_ws(websocket: WebSocket, document_id: uuid.UUID):
    """WebSocket endpoint for real-time document status updates"""

    ws_manager = WebSocketManager(websocket, document_id)
    if not await ws_manager.connect():
        return
    try:
        if not await ws_manager.send_initial_status():
            return

        await ws_manager.listen_for_updates()

    except WebSocketDisconnect:
        logger.info(f"WebSocket for document {document_id} disconnected by client")
    except asyncio.CancelledError:
        logger.info(f"WebSocket task cancelled for document {document_id}")
    except Exception as e:
        logger.error(f"Unexpected WebSocket error for document {document_id}: {e}")
        await ws_manager.send_message("error", message=f"Unexpected error: {str(e)}")
    finally:
        await ws_manager.disconnect()
