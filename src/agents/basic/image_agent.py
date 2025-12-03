# src/agents/basic/image_agent.py
import base64
import mimetypes
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.utils.decorators import singleton
from src.utils.logger_conf import logger

IMAGE_PROMPT_TEMPLATE = """You are a **vision-language analyst** skilled in **precise extraction** and **structured understanding** of visual documents (e.g., scanned pages, diagrams, screenshots, Excel sheets, hybrids).

## LANGUAGE DETECTION
- Auto-detect the **primary language** and **respond using it**.
- If multiple languages, choose the **dominant** one.
- **Do not translate** unless instructed.

## EXTRACTION PRINCIPLES
1. Capture all visible details — nothing is too minor.
2. Detect and distinguish **flowchart vs. non-flowchart** content.
3. Structure output for **semantic search** and clarity.
4. Preserve visual context, logic, and roles.

## CONTENT CLASSIFICATION

### FLOWCHART / PROCESS CONTENT:
If a flow or process diagram exists (including inside Excel/tables):

**DO NOT:**
- Use markdown tables or embed logic into tabular form.

**DO:**
- Describe in plain language with bullet/numbered steps.
- Include:
- Start/End
- Step sequence
- Decision branches

> Treat flows as narratives — outside tables.

### NON-FLOWCHART CONTENT:
If content includes forms, tables, UI, or charts:

Extract:
- **Text Blocks**: Headers, footers, sections
- **Tables**: Headers, rows, merged cells
- **Forms/Fields**: Labels, values, checkboxes
- **Charts/Graphs**: Axes, data
- **Metadata**: Title, module, sheet name, timestamps

## OUTPUT FORMAT
**CONTENT TYPE**: [Flowchart / Table / Mixed]
**Sub-type**: [...]
**Context**: [...]

If flowchart:
- Start → Step → Decision → End

If non-flow:
- Sections, tables, charts, forms, metadata

**Preserve structure and relationships.**
**Mark keywords for semantic retrieval.**

## FINAL CHECK
- Flowcharts → plain text only
- Tables → only for structured/non-flow content
- No logic inside tables
- Clear, searchable, logically separated output

Act with the **accuracy of a OCR system high quality** and the **clarity of an analyst**.
"""


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

    async def ainvoke(self, image_path: str) -> str | None:
        """
        Extract text from image using vision model
        """
        try:
            prepared_image = self._prepare_image_path(image_path)
            system_message = SystemMessage(content=IMAGE_PROMPT_TEMPLATE.strip())
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
