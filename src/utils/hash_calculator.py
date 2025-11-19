import hashlib

from fastapi import UploadFile


async def calculate_hash_from_stream(
    file: UploadFile, hash_algorithm: str = "sha256"
) -> str:
    """Calculates the hash of a file from a stream."""
    hasher = hashlib.new(hash_algorithm)
    await file.seek(0)

    while chunk := await file.read(8192):
        hasher.update(chunk)

    await file.seek(0)

    return hasher.hexdigest()


def get_content_hash(content: str) -> str:
    """
    Create a hash from content.
    """
    if not content:
        return ""
    cleaned_content = " ".join(content.split())
    return hashlib.md5(cleaned_content.encode("utf-8")).hexdigest()
