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
from src.utils.logger_conf import logger


class NaiveStrategy(BaseStrategy):
    """
    Naive document processing strategy that uses Langchain's document loaders directly.
    This strategy applies minimal processing and lets the document loaders handle most of the work.
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
            from langchain_pymupdf4llm import PyMuPDF4LLMLoader

            return PyMuPDF4LLMLoader(file_path)

        if file_extension == ".doc":
            from langchain_community.document_loaders import (
                UnstructuredWordDocumentLoader,
            )

            return UnstructuredWordDocumentLoader(file_path)

        if file_extension == ".ppt":
            from langchain_community.document_loaders import (
                UnstructuredPowerPointLoader,
            )

            return UnstructuredPowerPointLoader(file_path, include_slide_notes=True)
        # if file_extension == ".xlsx":
        #     from src.rag.processor.loader.xlsx_loader import CustomExcelLoader

        #     return CustomExcelLoader(file_path)
        if file_extension in [".jpg", ".jpeg", ".png"]:
            return ImageLoader(image_path=file_path, document=document)
        if file_extension in [".xml"]:
            from langchain_community.document_loaders import UnstructuredXMLLoader

            return UnstructuredXMLLoader(file_path, max_characters=1000000)
        if file_extension in [".rst"]:
            from langchain_community.document_loaders import UnstructuredRSTLoader

            return UnstructuredRSTLoader(file_path)

        # if file_extension in [".xls"]:
        #     return XlsLoader(file_path=file_path)
        # from langchain_community.document_loaders import UnstructuredExcelLoader

        # return UnstructuredExcelLoader(
        #     file_path,
        #     max_characters=1000000,
        #     include_header=True,
        #     find_subtable=True,
        # )
        if file_extension in [".csv"]:
            from langchain_community.document_loaders.csv_loader import CSVLoader

            # Use find_codec to determine the encoding of the CSV file
            return CSVLoader(file_path=file_path, autodetect_encoding=True)
        if file_extension in [".txt", ".md"]:
            from langchain_community.document_loaders import UnstructuredMarkdownLoader

            return UnstructuredMarkdownLoader(file_path, max_characters=1000000)

        if os.path.isdir(file_path):
            return DirectoryLoader(file_path)

        return UnstructuredFileLoader(
            file_path,
            encoding="utf-8",
            max_characters=1000000,
        )

    def chunk(self, file_path: str, document: DBDocument) -> List[Document]:
        """
        Process a file using Langchain's document loaders.

        Args:
            file_path: The path to the file to process

        Returns:
            A list of Langchain Document objects
        """
        logger.info(f"Processing file {file_path} with naive strategy")

        try:
            valid = self.check_file_type(file_path)
            if not valid:
                raise ValueError(f"Unsupported file type: {document.file_type}")
            # Get the appropriate loader based on file type
            loader = self._get_loader(file_path, document)

            # Load documents
            logger.info(
                f"Loading documents from {file_path} using {loader.__class__.__name__}"
            )

            docs = loader.lazy_load()

            if not docs:
                raise ValueError("The document has no readable content.")

            text_splitter = MarkdownTextSplitter(
                chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap
            )

            document_spliter = []
            unsplit_documents = []

            for doc in docs:
                splitter_value = doc.metadata.get("splitter", None)

                if splitter_value is False:
                    unsplit_documents.append(doc)
                else:
                    document_spliter.append(doc)

            splitter = text_splitter.split_documents(document_spliter)
            split_docs = unsplit_documents + splitter
            # Add file path and strategy metadata to each document
            for doc in split_docs:
                if "source" not in doc.metadata:
                    doc.metadata["source"] = file_path
                doc.metadata["strategy"] = "naive"

            logger.info(f"Created {len(split_docs)} chunks from {file_path}")

            return split_docs

        except Exception as e:
            logger.exception(f"Error processing file {file_path}: {str(e)}")
            raise


if __name__ == "__main__":
    config = {
        "chunk_size": 1900,
        "chunk_overlap": 500,
        "cluster_threshold": 0.4,
        "api_key": "sk-proj-1234567890",
        "model_name": "gpt-4o-mini",
        "api_url": "https://api.openai.com/v1",
    }
    strategy = NaiveStrategy(config)
    file_path = "data/test.xlsx"
    document = DBDocument(file_path=file_path, file_type="xlsx")
    chunks = strategy.chunk(file_path, document)
    print(chunks)
