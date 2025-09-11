from typing import List

from langchain_core.document_loaders.base import BaseLoader
from langchain_core.documents import Document

from src.agents.image_agent import ImageExtractionAgent
from src.config.settings import settings
from src.connector import minio_client
from src.db.models.document import Document as DBDocument
from src.utils.logger_conf import logger


class ImageLoader(BaseLoader):
    def __init__(self, image_path: str, document: DBDocument):
        super().__init__()
        self.image_path = image_path
        self.document = document
        self.agent = ImageExtractionAgent()

    async def load(self) -> List[Document]:
        """
        Load documents from the file.

        Returns:
            List of Document objects
        """

        return await self._load_text()

    async def _get_presigned_url(self):
        images_presigned_url = await minio_client.get_presigned_url(
            bucket_name=settings.minio_bucket,
            object_name=self.document.file_path,
            expires=settings.minio_presigned_url_expiration,
        )
        return images_presigned_url

    async def _load_text(self) -> List[Document]:
        """Load a text file."""
        try:
            content = self.agent.extract(await self._get_presigned_url())
            # filename = self.image_path.split("/")[-1]
            # full_text = f"The content of the {filename} image is \n : {full_text}"
            # ==== images token specific ====
            full_text = f"<|IMAGE|>{content}</|IMAGE|>"
            metadata = {"source": self.image_path, "images": [self.document.file_path]}
            return [Document(page_content=full_text, metadata=metadata)]
        except Exception:
            # Log error if needed
            logger.exception(f"Failed to extract text from image {self.image_path}")
            raise

    def create_empty_document(self) -> Document:
        return Document(
            page_content="", metadata={"source": self.image_path, "images": []}
        )
