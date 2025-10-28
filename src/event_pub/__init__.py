# src/event_pub/__init__.py
from src.event_pub.redis import RedisEventPublisher

publisher = RedisEventPublisher()


async def get_event_publisher():
    """
    Get the event publisher instance.

    Returns:
        The event publisher instance.
    """
    await publisher.connect()
    return publisher
