# src/domain/entities/streaming.py
import json
from typing import Any, Dict, Optional, Union

from src.domain.schemas.stream import StreamEvent, StreamEventType, StreamPhase


class StreamEventBuilder:
    """Builder for creating standardized stream events"""

    @staticmethod
    def create_sse_event(
        event_type: Union[StreamEventType, str],
        data: Dict[str, Any],
        event_id: Optional[str] = None,
    ) -> str:
        """Create SSE formatted event"""
        if isinstance(event_type, StreamEventType):
            event_type = event_type.value

        event = StreamEvent(type=event_type, data=data, id=event_id)

        sse_data = json.dumps(
            {
                **event.data,
                "id": event.id,
                "timestamp": event.timestamp,
            },
            ensure_ascii=False,
        )

        return f"event: {event.type}\ndata: {sse_data}\n\n"

    @staticmethod
    def message_start() -> str:
        """Start of message generation"""
        return StreamEventBuilder.create_sse_event(
            StreamEventType.MESSAGE_START, {"message": "Message generation started"}
        )

    @staticmethod
    def content_delta(text: str, index: int = 0) -> str:
        """Content chunk delta"""
        return StreamEventBuilder.create_sse_event(
            StreamEventType.MESSAGE_DELTA,
            {"delta": {"type": "text_delta", "text": text}, "index": index},
        )

    @staticmethod
    def status_update(
        phase: Union[StreamPhase, str],
        message: str,
        progress: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Status update"""
        if isinstance(phase, StreamPhase):
            phase = phase.value

        data = {
            "phase": phase,
            "message": message,
        }

        if progress is not None:
            data["progress"] = min(max(progress, 0.0), 1.0)

        if metadata:
            data["metadata"] = metadata

        return StreamEventBuilder.create_sse_event(StreamEventType.STATUS, data)

    @staticmethod
    def message_stop(
        final_message: Optional[str | Dict[str, Any]] = None,
        references: Optional[list] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """End of message"""
        data = {}

        if final_message:
            data["final_message"] = final_message

        if references:
            data["references"] = references

        if metadata:
            data["metadata"] = metadata

        return StreamEventBuilder.create_sse_event(StreamEventType.MESSAGE_STOP, data)

    @staticmethod
    def error(error_type: str, message: str, code: Optional[int] = None) -> str:
        """Error event"""
        data = {"type": error_type, "message": message}

        if code:
            data["code"] = code

        return StreamEventBuilder.create_sse_event(StreamEventType.ERROR, data)
