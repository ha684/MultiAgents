# src/tasks/qac.py
from uuid import UUID
from src.db.models.document import DocumentQA
from src.agents import qa_agent
from src.db import knowledge_base_repository, document_repository, qa_repository
from src.utils.logger_conf import logger
from typing import List


async def _generate_qa_pairs_async(
    document_id: UUID, kb_id: UUID, contexts: List[str]
) -> None:
    """
    Async helper function to generate QA pairs.

    Args:
        document_id (UUID): The ID of the document to process.
        kb_id (UUID): The ID of the knowledge base to store the QA pairs.
        contexts (List[str]): List of text contexts to generate QA pairs from.
    """
    if not contexts:
        logger.warning("No contexts provided for QA generation.")
        return

    kb = await knowledge_base_repository.get(kb_id)
    if not kb:
        raise ValueError(f"Knowledge Base with ID {kb_id} not found")

    document = await document_repository.get(document_id)
    if not document:
        raise ValueError(f"Document with ID {document_id} not found")

    await qa_repository.delete_qa_by_doc_id(document_id)

    qa_pairs = await qa_agent.generate_qa(contexts)

    if not qa_pairs:
        raise ValueError(f"No QA pairs generated for document {document_id}")

    qa_list = [
        DocumentQA(
            question=qa_pair[0],
            answer=qa_pair[1],
            document_id=document_id,
            kb_id=kb_id,
        )
        for qa_pair in qa_pairs
    ]

    await qa_repository.create_qa_list(qa_list)
