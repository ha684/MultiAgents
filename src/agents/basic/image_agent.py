import base64
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
import requests
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from src.config.llm_config import SupportedLLMProviders
from src.llm.factory import get_llm
from src.prompts.get_prompt_template import load_prompt_template
from src.utils.decorators import singleton


@singleton
class ImageExtractionAgent:
    def __init__(self, provider: SupportedLLMProviders = "nxchat-vision"):
        self.llm = get_llm(provider)

    def _prepare_image_path(self, image_path: str, use_base64: bool = True) -> str:
        """
        Prepare image path for the LLM. Can either convert to base64 or format as file:// URL.

        Args:
            image_path (str): Path to the image file or URL
            use_base64 (bool): Whether to convert to base64 or use file:// format

        Returns:
            str: Prepared image path/data for the LLM
        """
        parsed_url = urlparse(image_path)

        # If it's already a HTTP/HTTPS URL, return as-is
        if parsed_url.scheme in ("http", "https"):
            if use_base64:
                return self._convert_url_to_base64(image_path)
            return image_path

        # Handle local file paths
        file_path = image_path.replace("file://", "")
        path_obj = Path(file_path)

        if not path_obj.exists():
            raise FileNotFoundError(f"Image file not found: {file_path}")

        if use_base64:
            return self._convert_file_to_base64(path_obj)
        else:
            # Use native file:// support
            return f"file://{path_obj.absolute()}"

    def _convert_file_to_base64(self, file_path: Path) -> str:
        """Convert local file to base64 data URL."""
        with open(file_path, "rb") as image_file:
            image_data = image_file.read()

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type or not mime_type.startswith("image/"):
            mime_type = "image/jpeg"

        base64_data = base64.b64encode(image_data).decode("utf-8")
        return f"data:{mime_type};base64,{base64_data}"

    def _convert_url_to_base64(self, url: str) -> str:
        """Convert URL to base64 data URL."""
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        mime_type = response.headers.get("content-type", "image/jpeg")
        if not mime_type.startswith("image/"):
            mime_type = "image/jpeg"

        base64_data = base64.b64encode(response.content).decode("utf-8")
        return f"data:{mime_type};base64,{base64_data}"

    def extract(self, image_url: str, use_base64: bool = True) -> str | None:
        """
        Extract context from an image URL using a language model.
        image_url (str): The URL or path of the image to be processed.
        use_base64 (bool): Whether to convert to base64 or use native file:// support.
                        True = Always convert to base64 (works across machines)
                        False = Use native file:// support (faster, but only works locally)
        """
        try:
            # Prepare the image path/data
            prepared_image = self._prepare_image_path(image_url, use_base64)

            prompt_template = load_prompt_template(
                task_name="image_to_text",
            )
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", prompt_template.strip()),
                    (
                        "human",
                        [
                            {"type": "text", "text": prompt_template.strip()},
                            {
                                "type": "image",
                                "image": prepared_image,
                            },
                        ],
                    ),
                ]
            )

            chain = prompt | self.llm | StrOutputParser()
            chain = chain.with_retry()
            content = chain.invoke({})

            if not content:
                raise ValueError("No content returned from LLM response")

        except FileNotFoundError as e:
            raise RuntimeError(f"Image file not found: {str(e)}")
        except requests.RequestException as e:
            raise RuntimeError(f"Error downloading image: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Error generating QA: {str(e)}")

        return content.strip() if content else None
