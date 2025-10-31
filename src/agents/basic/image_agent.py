# src/agents/basic/image_agent.py
import base64
import mimetypes
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.agents.prompts.get_prompt_template import load_prompt_template
from src.utils.decorators import singleton
from src.utils.logger_conf import logger


@singleton
class ImageExtractionAgent(BaseAgent):
    def __init__(self):
        super().__init__("nxchat-vision")

    def _prepare_image_path(self, image_path: str) -> str:
        """
        Prepare image path for the LLM
        """
        path_obj = Path(image_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")
        return self._convert_file_to_base64(path_obj)

    def _convert_file_to_base64(self, file_path: Path) -> str:
        """Convert local file to base64 data URL."""
        with open(file_path, "rb") as image_file:
            image_data = image_file.read()

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type or not mime_type.startswith("image/"):
            mime_type = "image/jpeg"

        base64_data = base64.b64encode(image_data).decode("utf-8")
        return f"data:{mime_type};base64,{base64_data}"

    async def extract(self, image_path: str) -> str | None:
        """
        Extract text from image using vision model
        """
        try:
            prepared_image = self._prepare_image_path(image_path)
            prompt_template = load_prompt_template(task_name="image_to_text")

            system_message = SystemMessage(content=prompt_template.strip())
            human_message = HumanMessage(
                content=[
                    {"type": "text", "text": "Extract text from image"},
                    {"type": "image_url", "image_url": {"url": prepared_image}},
                ]
            )

            messages = [system_message, human_message]

            response = await self.simple_llm_call(messages)

            if not response.content:
                raise ValueError("No content returned from LLM response")

            return response.content

        except Exception as e:
            logger.error(f"Error extracting text from image: {str(e)}")
            raise RuntimeError(f"Error when extracting text from image: {str(e)}")
