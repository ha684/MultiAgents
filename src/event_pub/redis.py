# src/event_pub/redis.py
import json
import asyncio

from src.utils.decorators import singleton
from src.event_pub.base import BaseEventPublisher
from src.event_pub.redis_client import get_redis
from src.utils.logger_conf import logger


@singleton
class RedisEventPublisher(BaseEventPublisher):
    """
    Concrete implementation of AbstractEventPublisher using Redis Pub/Sub.
    """

    def __init__(self):
        self.redis_client = None

    async def connect(self):
        """
        Establishes a connection to the Redis server.
        """
        try:
            redis_client = await get_redis()
            self.redis_client = redis_client
            await self.redis_client.ping()
            logger.info("RedisEventPublisher: Successfully connected to Redis.")
        except Exception:
            raise ConnectionError(
                "Could not connect to Redis. Run docker compose first"
            )

    async def disconnect(self):
        """
        Closes the connection to the Redis server.
        """
        try:
            if self.redis_client:
                await self.redis_client.aclose()
                self.redis_client = None
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
            # The publish command returns the number of subscribers that received the message
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
        pubsub.subscribe(channel)
        logger.info(f"RedisEventPublisher: Subscribed to channel '{channel}'")

        try:
            while True:
                # Use asyncio.sleep to yield control and make this non-blocking
                await asyncio.sleep(0.01)  # Small delay to prevent busy waiting

                # Get message with a timeout to avoid blocking
                message = pubsub.get_message(timeout=0.01)

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
                pubsub.unsubscribe(channel)
                pubsub.close()
                logger.info(
                    f"RedisEventPublisher: Unsubscribed from channel '{channel}'"
                )
            except Exception as e:
                logger.warning(f"RedisEventPublisher: Error during cleanup: {e}")
