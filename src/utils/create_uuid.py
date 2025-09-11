import uuid


def create_uuid() -> uuid.UUID:
    """
    Create a UUID that includes the current timestamp (UUIDv1).
    """
    return uuid.uuid1()
