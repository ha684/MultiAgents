# src/event_pub/__init__.py
from src.event_pub.redis import RedisEventPublisher


def get_event_publisher():
    """
    Get the event publisher instance.

    Returns:
        The event publisher instance.
    """
    publisher = RedisEventPublisher()
    publisher.connect()
    return publisher


event_publisher = get_event_publisher()
