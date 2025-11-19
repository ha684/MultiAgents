# src/domain/schemas/qa.py

from uuid import UUID

from pydantic import BaseModel


class DocumentQAResponse(BaseModel):
    """
    Represents the response for a document question-answering task.
    """

    question: str
    answer: str
    document_id: UUID
    kb_id: UUID
