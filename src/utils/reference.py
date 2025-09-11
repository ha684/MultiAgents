import re
from typing import List
from langchain_core.documents import Document
from src.utils.logger_conf import logger


def _replace_image_token(
    match: re.Match, images_url_mapping: list, image_counter: int
) -> str:
    if image_counter < len(images_url_mapping):
        image_url = images_url_mapping[image_counter]
        image_counter += 1
        return f"<|IMAGE|>{image_url}</|IMAGE|>"
    else:
        original_content = match.group(1).strip()
        return f"<|IMAGE|>[Missing content for {original_content}]</|IMAGE|>"


def _normalize_image_ref(document: Document):
    image_url = document.metadata["images"][0]
    new_content = f"<|IMAGE|>{image_url}</|IMAGE|>"
    document.page_content = new_content
    return document


def _normalize_doc_ref(document: Document) -> Document:
    image_counter = 0
    images = document.metadata.get("images", [])

    images_url_mapping = []
    for image in images:
        images_url_mapping.append(image)
    pattern = r"<\|IMAGE\|>(.*?)</\|IMAGE\|>"
    updated_text = re.sub(
        pattern,
        lambda match: _replace_image_token(match, images_url_mapping, image_counter),
        document.page_content,
    )

    document.page_content = updated_text
    return document


def normalize_ref_images(document: Document) -> Document:
    if not document.metadata.get("images", []):
        return document
    else:
        try:
            file_name = document.metadata["filename"]
            file_type = file_name.split(".")[-1].lower()
            if file_type in ["jpg", "jpeg", "png"]:
                document = _normalize_image_ref(document=document)
            else:
                document = _normalize_doc_ref(document=document)
            return document
        except Exception as e:
            logger.info(
                f"**** Error in processing reformat structure images chunk : {e}"
            )
            document = _normalize_doc_ref(
                document=document,
            )
            return document


def normalize_ref_table(document: Document) -> Document:
    sheet_name = document.metadata.get("sheet_name", None)
    if sheet_name:
        logger.info(f"Normalizing table references in document: {sheet_name}")
        document.page_content = document.page_content.replace("\\\\n", "<br>")
    return document


def normalize_ref(
    documents: List[Document],
    normalize_images: bool = True,
    normalize_table: bool = True,
) -> List[Document]:
    """
    Normalize references in the documents by replacing image tokens and formatting table references.

    Args:
        documents: A list of Document objects to normalize.

    Returns:
        A list of normalized Document objects.
    """
    new_list_documents = []
    for document in documents:
        document = (
            normalize_ref_images(document=document) if normalize_images else document
        )
        document = (
            normalize_ref_table(document=document) if normalize_table else document
        )
        new_list_documents.append(document)
    return new_list_documents
