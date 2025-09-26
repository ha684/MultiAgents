import hashlib
from fastapi import UploadFile


async def calculate_hash_from_stream(
    file: UploadFile, hash_algorithm: str = "sha256"
) -> str:
    """Calculates the hash of a file from a stream."""
    hasher = hashlib.new(hash_algorithm)
    # Reset file pointer to the beginning
    await file.seek(0)

    # Read file in chunks to avoid high memory usage
    while chunk := await file.read(8192):  # Read in 8KB chunks
        hasher.update(chunk)

    # Reset file pointer again so it can be read by other functions
    await file.seek(0)

    return hasher.hexdigest()
