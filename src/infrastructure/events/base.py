# src/infrastructure/events/base.py
import abc
import json


class BaseEventPublisher(abc.ABC):
    """
    Abstract Base Class for an event publisher.

    Defines the contract for publishing events to a message broker,
    allowing different broker implementations to be swapped out easily.
    """

    @abc.abstractmethod
    def connect(self):
        """Establishes a connection to the event broker."""
        raise NotImplementedError(
            "Connect method must be implemented by concrete classes."
        )

    @abc.abstractmethod
    def disconnect(self):
        """Closes the connection to the event broker."""
        raise NotImplementedError(
            "Disconnect method must be implemented by concrete classes."
        )

    @abc.abstractmethod
    def publish(self, channel: str, event_data: dict):
        """
        Publishes an event to a specified channel.

        Args:
            channel (str): The name of the channel/topic to publish to.
            event_data (dict): The event payload as a dictionary. This will
                               typically be serialized to a string (e.g., JSON)
                               before sending.
        """
        raise NotImplementedError(
            "Publish method must be implemented by concrete classes."
        )

    @abc.abstractmethod
    async def subscribe(self, channel: str):
        """
        Subscribes to a specified channel and yields events asynchronously.

        Args:
            channel (str): The name of the channel/topic to subscribe to.

        Yields:
            dict: Event data received from the channel.
        """
        raise NotImplementedError(
            "Subscribe method must be implemented by concrete classes."
        )

    @staticmethod
    def _serialize_event(event_data: dict) -> str:
        """Helper method to serialize event data to a JSON string."""
        try:
            return json.dumps(event_data)
        except TypeError as e:
            raise ValueError(f"Event data must be JSON serializable: {e}") from e

    @staticmethod
    def _deserialize_event(message: str) -> dict:
        """Helper method to deserialize a JSON string back to a dictionary."""
        try:
            return json.loads(message)
        except json.JSONDecodeError as e:
            raise ValueError(f"Received message is not valid JSON: {e}") from e
