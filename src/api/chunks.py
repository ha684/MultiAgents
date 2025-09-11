from typing import List
from langchain_core.documents import Document
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from src.services.chunks_service import ChunksService

router = APIRouter(prefix="/chunks", tags=["Chunks"])
chunks_service = ChunksService()


class ChunkIdsRequest(BaseModel):
    chunk_ids: List[str]


@router.get("/")
async def get_chunks(
    document_id: str = Query(..., description="Filter chunks by document ID"),
) -> List[Document]:
    """
    Get all chunks for a specific document.

    Args:
        document_id: The document ID to filter chunks by

    Returns:
        List of chunks belonging to the document
    """
    if not document_id:
        raise HTTPException(status_code=400, detail="Document ID is required")
    chunks = await chunks_service.get_chunks_by_doc_id(document_id)
    if not chunks:
        raise HTTPException(status_code=404, detail="No chunks found for this document")
    return chunks


@router.get("/ids")
async def get_chunk_ids(
    document_id: str = Query(..., description="Get chunk IDs for this document"),
) -> List[str]:
    """
    Get only the chunk IDs for a specific document.

    Args:
        document_id: The document ID to get chunk IDs for

    Returns:
        List of chunk IDs belonging to the document
    """
    if not document_id:
        raise HTTPException(status_code=400, detail="Document ID is required")
    chunk_ids = await chunks_service.get_chunk_ids_by_doc_id(document_id)
    if not chunk_ids:
        raise HTTPException(
            status_code=404, detail="No chunk IDs found for this document"
        )
    return chunk_ids


@router.post("/batch")
async def get_chunks_by_ids(request: ChunkIdsRequest) -> List[Document]:
    """
    Retrieve multiple chunks by their IDs.

    Args:
        request: Request body containing a list of chunk IDs to retrieve.

    Returns:
        A list of Document objects corresponding to the provided chunk IDs.
    """
    return await chunks_service.get_chunks_by_ids(request.chunk_ids)


@router.get("/{chunk_id}")
async def get_chunk_by_id(chunk_id: str) -> Document:
    """Get a single chunk by its ID."""
    if not chunk_id:
        raise HTTPException(status_code=400, detail="Chunk ID is required")
    chunk = await chunks_service.get_chunk_by_id(chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    return chunk
