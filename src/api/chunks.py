# src/api/chunks.py
from typing import List
from langchain_core.documents import Document
from fastapi import APIRouter
from pydantic import BaseModel
from src.services.chunks_service import ChunksService

router = APIRouter(prefix="/chunks", tags=["Chunks"])
chunks_service = ChunksService()


class ChunkIdsRequest(BaseModel):
    chunk_ids: List[str]


@router.get("/")
async def get_chunks(
    document_id: str,
) -> List[Document]:
    """
    Get all chunks for a specific document.

    Args:
        document_id: The document ID to filter chunks by

    Returns:
        List of chunks belonging to the document
    """
    try:
        chunks = await chunks_service.get_chunks_by_doc_id(document_id)
        return chunks
    except Exception as e:
        raise e


@router.get("/ids")
async def get_chunk_ids(
    document_id: str,
) -> List[str]:
    """
    Get only the chunk IDs for a specific document.

    Args:
        document_id: The document ID to get chunk IDs for

    Returns:
        List of chunk IDs belonging to the document
    """
    try:
        chunk_ids = await chunks_service.get_chunk_ids_by_doc_id(document_id)
        return chunk_ids
    except Exception as e:
        raise e


@router.post("/batch")
async def get_chunks_by_ids(request: ChunkIdsRequest) -> List[Document]:
    """
    Retrieve multiple chunks by their IDs.

    Args:
        request: Request body containing a list of chunk IDs to retrieve.

    Returns:
        A list of Document objects corresponding to the provided chunk IDs.
    """
    try:
        return await chunks_service.get_chunks_by_ids(request.chunk_ids)
    except Exception as e:
        raise e


@router.get("/{chunk_id}")
async def get_chunk_by_id(chunk_id: str) -> Document:
    """Get a single chunk by its ID."""
    try:
        chunk = await chunks_service.get_chunk_by_id(chunk_id)
        return chunk
    except Exception as e:
        raise e
