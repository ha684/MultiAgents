from pathlib import Path
from langchain_core.documents import Document
from langchain_community.document_loaders import DirectoryLoader, UnstructuredFileLoader
from langchain_community.document_loaders.base import BaseLoader
from langchain.text_splitter import MarkdownTextSplitter
import os
from typing import List, Dict, Any, Optional
from src.rag.processor.strategy.base import BaseStrategy
from src.rag.processor.loader.images_loader import ImageLoader
from src.db.models.document import Document as DBDocument
from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_community.document_loaders import UnstructuredWordDocumentLoader
from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain_community.document_loaders import UnstructuredPowerPointLoader
from langchain_community.document_loaders import UnstructuredXMLLoader
from langchain_community.document_loaders import UnstructuredRSTLoader
from langchain_community.document_loaders.csv_loader import CSVLoader
from src.rag.processor.strategy.spreadsheet import SpreadsheetStrategy
from src.utils.logger_conf import logger


class NaiveStrategy(BaseStrategy):
    """
    Naive document processing strategy that uses Langchain's document loaders directly.
    This strategy applies minimal processing and lets the document loaders handle most of the work.
    Includes deep citation support with start and end character indices.
    """

    _supported_file_types = [
        "pdf",
        "jpg",
        "jpeg",
        "png",
        "docx",
        "doc",
        "txt",
        "md",
        "pptx",
        "ppt",
        "xlsx",
        "xls",
        "rst",
        "xml",
        "csv",
    ]

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the naive strategy.

        Args:
            config: A dictionary with the configuration parameters
                - chunk_size: The size of each chunk
                - chunk_overlap: The overlap between chunks
        """
        super().__init__(
            config,
        )
        self.chunk_size = config.get("chunk_size", 1800)
        self.chunk_overlap = config.get("chunk_overlap", 180)

    def _get_loader(self, file_path: str, document: Optional[DBDocument]) -> BaseLoader:
        """
        Get the appropriate document loader based on the file type.

        Args:
            file_path: The path to the file

        Returns:
            A Langchain document loader
        """
        file_extension = Path(file_path).suffix.lower()
        logger.info(
            f"Determining loader for file {file_path} with extension {file_extension}"
        )
        if file_extension == ".pdf":
            return PyMuPDF4LLMLoader(file_path)
        if file_extension == ".doc":
            return UnstructuredWordDocumentLoader(file_path)
        if file_extension == ".ppt":
            return UnstructuredPowerPointLoader(file_path, include_slide_notes=True)
        if file_extension in [".jpg", ".jpeg", ".png"]:
            return ImageLoader(image_path=file_path, document=document)
        if file_extension in [".xml"]:
            return UnstructuredXMLLoader(file_path, max_characters=1000000)
        if file_extension in [".rst"]:
            return UnstructuredRSTLoader(file_path)
        if file_extension in [".csv"]:
            return CSVLoader(file_path=file_path, autodetect_encoding=True)
        if file_extension in [".txt", ".md"]:
            return UnstructuredMarkdownLoader(file_path, max_characters=1000000)
        if file_extension in [".xlsx", ".xls"]:
            return SpreadsheetStrategy(config=self.config)
        if os.path.isdir(file_path):
            return DirectoryLoader(file_path)
        return UnstructuredFileLoader(
            file_path,
            encoding="utf-8",
            max_characters=1000000,
        )

    def _add_citation_metadata(
        self, documents: List[Document], full_text: str
    ) -> List[Document]:
        """
        Add start and end character indices to document metadata for deep citation.

        Args:
            documents: List of chunked documents
            full_text: The complete text of the original document

        Returns:
            Documents with added citation metadata
        """
        current_position = 0

        for doc in documents:
            chunk_text = doc.page_content
            start_index = full_text.find(chunk_text, current_position)

            if start_index != -1:
                end_index = start_index + len(chunk_text)
                doc.metadata["start_index"] = start_index
                doc.metadata["end_index"] = end_index
                current_position = start_index + len(chunk_text) - self.chunk_overlap
            else:
                logger.warning(
                    f"Could not find exact match for chunk starting with: "
                    f"{chunk_text[:50]}... Using approximate position."
                )
                doc.metadata["start_index"] = current_position
                doc.metadata["end_index"] = current_position + len(chunk_text)
                current_position += len(chunk_text) - self.chunk_overlap

        return documents

    def chunk(self, file_path: str, document: DBDocument) -> List[Document]:
        """
        Process a file using Langchain's document loaders with deep citation support.

        Args:
            file_path: The path to the file to process
            document: The database document object

        Returns:
            A list of Langchain Document objects with citation metadata
        """
        logger.info(f"Processing file {file_path} with naive strategy")

        try:
            valid = self.check_file_type(file_path)
            if not valid:
                raise ValueError(f"Unsupported file type: {document.file_type}")

            loader = self._get_loader(file_path, document)
            logger.info(
                f"Loading documents from {file_path} using {loader.__class__.__name__}"
            )
            docs = list(loader.lazy_load())

            if not docs:
                raise ValueError("The document has no readable content.")

            full_text = "\n\n".join([doc.page_content for doc in docs])

            text_splitter = MarkdownTextSplitter(
                chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap
            )

            document_spliter: List[Document] = []
            unsplit_documents: List[Document] = []

            for doc in docs:
                splitter_value = doc.metadata.get("splitter", None)

                if splitter_value is False:
                    unsplit_documents.append(doc)
                else:
                    document_spliter.append(doc)

            splitter = text_splitter.split_documents(document_spliter)

            if splitter:
                splitter = self._add_citation_metadata(splitter, full_text)

            for doc in unsplit_documents:
                start_index = full_text.find(doc.page_content)
                if start_index != -1:
                    doc.metadata["start_index"] = start_index
                    doc.metadata["end_index"] = start_index + len(doc.page_content)
                else:
                    doc.metadata["start_index"] = 0
                    doc.metadata["end_index"] = len(doc.page_content)

            split_docs = unsplit_documents + splitter

            for doc in split_docs:
                if "source" not in doc.metadata:
                    doc.metadata["source"] = file_path
                doc.metadata["strategy"] = "naive"

            logger.info(
                f"Created {len(split_docs)} chunks from {file_path} with citation metadata"
            )

            return split_docs

        except Exception as e:
            logger.exception(f"Error processing file {file_path}: {str(e)}")
            raise e
