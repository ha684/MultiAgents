from src.common.types import Message
from src.utils.logger_conf import logger


def get_message_id(m: Message | None) -> str | None:
    """Get message ID with error handling"""
    try:
        if not m or not m.metadata or "message_id" not in m.metadata:
            return None
        return m.metadata["message_id"]
    except Exception as e:
        logger.error(f"Error getting message ID: {e}")
        return None


def get_last_message_id(m: Message | None) -> str | None:
    """Get last message ID with error handling"""
    try:
        if not m or not m.metadata or "last_message_id" not in m.metadata:
            return None
        return m.metadata["last_message_id"]
    except Exception as e:
        logger.error(f"Error getting last message ID: {e}")
        return None
