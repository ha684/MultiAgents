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
