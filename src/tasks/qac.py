# src/tasks/qac.py
from uuid import UUID

from src.agents.basic import qac_agent
from src.database import document_repository, knowledge_base_repository, qa_repository
from src.database.models.document import DocumentQA
from src.utils.logger_conf import logger


def generate_qa_pairs(document_id: UUID, kb_id: UUID, full_text: str) -> None:
    """
    Generate QA pairs asynchronously.
    """
    if not full_text:
        logger.warning("No contexts provided for QA generation.")
        return

    kb = knowledge_base_repository.get(kb_id)
    if not kb:
        raise ValueError(f"Knowledge Base with ID {kb_id} not found")

    document = document_repository.get(document_id)
    if not document:
        raise ValueError(f"Document with ID {document_id} not found")

    qa_repository.delete_qa_by_doc_id(document_id)

    qa_pairs = qac_agent.ainvoke(full_text)
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

    qa_repository.create_qa_list(qa_list)
