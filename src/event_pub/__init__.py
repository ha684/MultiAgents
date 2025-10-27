# src/event_pub/__init__.py
import asyncio
from src.event_pub.redis import RedisEventPublisher


async def get_event_publisher():
    """
    Get the event publisher instance.

    Returns:
        The event publisher instance.
    """
    publisher = RedisEventPublisher()
    await publisher.connect()
    return publisher


event_publisher = asyncio.run(get_event_publisher())
