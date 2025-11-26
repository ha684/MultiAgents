# src/rag/processors/strategy/image.py
from pathlib import Path
from typing import Any

from langchain_core.documents import Document as LangchainDocument

from src.database.models.document import Document as DBDocument
from src.rag.processors.loader.images_loader import ImageLoader
from src.rag.processors.strategy.base import BaseStrategy
from src.utils.logger_conf import logger


class ImageStrategy(BaseStrategy):
    """
    Image processing strategy that uses Custom ImageLoader to process image files.
    """

    _supported_file_types = ["jpg", "jpeg", "png"]

    def __init__(self, config: dict[str, Any]):
        super().__init__(
            config,
        )

    def _get_loader(self, file_path: str, document: DBDocument) -> ImageLoader:
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

        return ImageLoader(image_path=file_path)

    async def chunk(
        self, file_path: str, document: DBDocument
    ) -> tuple[list[LangchainDocument], str]:
        """
        Process a file using Langchain's LangchainDocument loaders.

        Args:
            file_path: The path to the file to process

        Returns:
            A list of Langchain LangchainDocument objects
        """
        logger.info(f"Processing file {file_path} with naive strategy")

        try:
            valid = self.check_file_type(file_path)
            if not valid:
                raise ValueError(f"Unsupported file type: {document.file_type}")
            loader = self._get_loader(file_path, document)
            if not loader:
                raise ValueError(f"Unsupported file type: {file_path}")

            logger.info(
                f"Loading documents from {file_path} using {loader.__class__.__name__}"
            )
            docs = await loader.lazy_load()
            full_text = "\n\n".join([doc.page_content for doc in docs])
            for doc in docs:
                if "source" not in doc.metadata:
                    doc.metadata["source"] = file_path

            logger.info(
                f"Loaded {len(docs)} documents from {file_path} using {loader.__class__.__name__}"
            )

            return docs, full_text

        except Exception as e:
            logger.exception(f"Error processing file {file_path}: {str(e)}")
            raise
