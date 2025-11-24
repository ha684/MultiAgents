# src/rag/processors/loader/images_loader.py
import textwrap

from langchain_core.document_loaders.base import BaseLoader
from langchain_core.documents import Document

from src.agents.basic.image_agent import ImageExtractionAgent
from src.utils.logger_conf import logger


class ImageLoader(BaseLoader):
    def __init__(self, image_path: str):
        super().__init__()
        self.image_path = image_path
        self.agent = ImageExtractionAgent()

    async def lazy_load(self) -> list[Document]:
        """
        Load documents from the file.
        """
        return await self._load_text()

    async def _load_text(self) -> list[Document]:
        """Load a text file."""
        try:
            content = await self.agent.ainvoke(self.image_path)
            full_text = textwrap.dedent(
                f"""\
                This is an image. The content extracted from the image is: <|IMAGE|>{content}</|IMAGE|>."
                If user asked something about the content in this image, you should mention about the content is retrieved from a image when response.
            """
            )
            metadata = {"source": self.image_path, "images": [self.image_path]}
            return [Document(page_content=full_text, metadata=metadata)]
        except Exception:
            logger.exception(f"Failed to extract text from image {self.image_path}")
            raise
