# src/infrastructure/events/redis_publisher.py
import asyncio
import json

from src.infrastructure.cache import redis_client
from src.infrastructure.events.base import BaseEventPublisher
from src.utils.decorators import singleton
from src.utils.logger_conf import logger


@singleton
class RedisEventPublisher(BaseEventPublisher):
    """
    Concrete implementation of AbstractEventPublisher using Redis Pub/Sub.
    """

    def __init__(self):
        self.redis_client = redis_client.get()

    async def disconnect(self):
        """
        Closes the connection to the Redis server.
        """
        try:
            await self.redis_client.aclose()
            logger.info("RedisEventPublisher: Disconnected from Redis.")
        except Exception:
            logger.warning("RedisEventPublisher: Error during disconnection.")

    async def publish(self, channel: str, event_data: dict):
        """
        Publishes an event to a specified Redis channel.

        Args:
            channel (str): The name of the channel to publish to.
            event_data (dict): The event payload as a dictionary.
        """
        try:
            message = self._serialize_event(event_data)
            subscribers_count = await self.redis_client.publish(channel, message)
            logger.info(
                f"RedisEventPublisher: Published to '{channel}': {message} (Subscribers: {subscribers_count})"
            )
        except ValueError as e:
            logger.exception(f"RedisEventPublisher: Serialization error: {e}")
        except Exception as e:
            logger.exception(
                f"RedisEventPublisher: An unexpected error occurred during publish: {e}"
            )

    async def subscribe(self, channel: str):
        """
        Subscribes to a specified Redis channel asynchronously.
        """
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe(channel)
        logger.info(f"RedisEventPublisher: Subscribed to channel '{channel}'")

        try:
            while True:
                # Use asyncio.sleep to yield control and make this non-blocking
                await asyncio.sleep(0.01)  # Small delay to prevent busy waiting

                # Get message with a timeout to avoid blocking
                message = await pubsub.get_message(timeout=0.01)

                if message is None:
                    continue

                if message["type"] == "message":
                    try:
                        event_data = json.loads(message["data"])
                        logger.debug(
                            f"RedisEventPublisher: Received message on '{channel}': {event_data}"
                        )
                        yield event_data
                    except json.JSONDecodeError as e:
                        logger.warning(
                            f"RedisEventPublisher: Failed to decode message: {e}"
                        )
                        continue

        except Exception as e:
            logger.exception(f"RedisEventPublisher: Error in subscribe loop: {e}")
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
                logger.info(
                    f"RedisEventPublisher: Unsubscribed from channel '{channel}'"
                )
            except Exception as e:
                logger.warning(f"RedisEventPublisher: Error during cleanup: {e}")
