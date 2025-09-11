from src.config import settings
from src.event_pub.redis import RedisEventPublisher

def get_event_publisher():
    """
    Get the event publisher instance.

    Returns:
        The event publisher instance.
    """
    publisher = RedisEventPublisher(
        uri=settings.redis_uri,
    )
    publisher.connect()
    return publisher

event_publisher = get_event_publisher()