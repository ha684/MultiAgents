# src/infrastructure/events/__init__.py
from src.infrastructure.events.redis_publisher import RedisEventPublisher

publisher = RedisEventPublisher()


async def get_event_publisher():
    """
    Get the event publisher instance.

    Returns:
        The event publisher instance.
    """
    return publisher
