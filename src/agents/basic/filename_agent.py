# src/agents/basic/filename_agent.py
import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.utils.logger_conf import logger

EXTRACT_FILENAME_PROMPT = """
You are an AI assistant that extracts the filename from a given arbitrary query. If
no filename is present, return null.
Your response should be a JSON object with a single key "filename" and the value
being the extracted filename or null if no filename is found.
The filename should include the file extension and should be a string without whitespace.

DO NOT include any additional text or explanations in your response.
DO NOT extract filename if the query mentions sheet names or specific content

# OUTPUT
{{
    "filename": "<filename>"
}}

Example:
# INPUT
"What is the content of the file document.pdf?"
# OUTPUT
{{
    "filename": "document.pdf"
}}

Example:
# INPUT
"Please upload the file report.docx for review."
# OUTPUT
{{
    "filename": "report.docx"
}}

Example:
# INPUT
"Who is the author of the book 'The Great Gatsby'?"
# OUTPUT
{{
    "filename": null
}}

Example:
# INPUT
"Thông tin ảnh 03.png"
# OUTPUT
{{
    "filename": "03.png"
}}
"""


class FileNameAgent(BaseAgent):
    def __init__(self):
        super().__init__()

    async def ainvoke(self, query: str) -> str | None:
        """
        Extract the filename from a given query.

        Args:
            query (str): The input query from which to extract the filename.

        Returns:
            str | None: The extracted filename or None if no filename is found.
        """

        try:
            system_prompt = SystemMessage(content=EXTRACT_FILENAME_PROMPT)
            user_prompt = HumanMessage(content=query)
            messages = [system_prompt, user_prompt]
            response = await self.simple_llm_call(messages)
            filename = json.loads(response.content)["filename"]
            return filename
        except Exception as e:
            logger.exception(f"Error extracting filename: {str(e)}")
            return None
