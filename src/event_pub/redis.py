from typing import Optional
import redis
import json
import asyncio
from src.utils.decorators import singleton
from .base import BaseEventPublisher
from urllib.parse import urlparse
from src.utils.logger_conf import logger


@singleton
class RedisEventPublisher(BaseEventPublisher):
    """
    Concrete implementation of AbstractEventPublisher using Redis Pub/Sub.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        uri: Optional[str] = "redis://redis:6379/0",
    ):
        """
        Initializes the RedisEventPublisher with connection parameters.

        Args:
            host (str): The Redis server host.
            port (int): The Redis server port.
            db (int): The Redis database number.
        """

        if uri:
            parsed_uri = urlparse(uri)
            host = parsed_uri.hostname or host
            port = parsed_uri.port or port
            db = int(parsed_uri.path.lstrip("/")) or db

        self.host = host
        self.port = port
        self.db = db
        self.redis_client = None
        logger.info(
            f"RedisEventPublisher: Initialized for {self.host}:{self.port}/{self.db}"
        )

    def connect(self):
        """
        Establishes a connection to the Redis server.
        """
        if self.redis_client is None:
            try:
                # decode_responses=True ensures that retrieved data is decoded to strings
                # from bytes automatically. This is useful for pub/sub messages as well.
                self.redis_client = redis.StrictRedis(
                    host=self.host, port=self.port, db=self.db, decode_responses=True
                )
                self.redis_client.ping()
                logger.info("RedisEventPublisher: Successfully connected to Redis.")
            except Exception:
                self.redis_client = None
                raise ConnectionError(
                    f"Could not connect to Redis at {self.host}:{self.port}, Run docker compose first"
                )
        else:
            logger.warning("RedisEventPublisher: Already connected.")

    def disconnect(self):
        """
        Closes the connection to the Redis server.
        """
        if self.redis_client:
            try:
                # For redis-py, there isn't a direct `close()` on StrictRedis
                # that explicitly shuts down underlying connections in a simple way
                # when not using connection pools explicitly. Nulling the client
                # reference is usually sufficient for graceful shutdown in simple cases.
                # In production, proper connection pool management is key.
                self.redis_client = None
                logger.info(
                    "RedisEventPublisher: Disconnected from Redis (client nulled)."
                )
            except Exception:
                logger.warning("RedisEventPublisher: Error during disconnection.")
        else:
            logger.warning("RedisEventPublisher: Not connected.")

    def publish(self, channel: str, event_data: dict):
        """
        Publishes an event to a specified Redis channel.

        Args:
            channel (str): The name of the channel to publish to.
            event_data (dict): The event payload as a dictionary.
        """
        if not self.redis_client:
            logger.info("RedisEventPublisher: Not connected. Cannot publish event.")
            return

        try:
            message = self._serialize_event(event_data)
            # The publish command returns the number of subscribers that received the message
            subscribers_count = self.redis_client.publish(channel, message)
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
        if not self.redis_client:
            logger.info("RedisEventPublisher: Not connected. Cannot subscribe.")
            return

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
