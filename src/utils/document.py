import uuid


def generate_chunk_id(document_id: str, chunk_id: str) -> str:
    """
    Generate a deterministic unique UUID for a document chunk.
    """

    return uuid.uuid5(uuid.UUID(document_id), chunk_id).hex
