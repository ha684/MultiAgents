from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from src.llm.factory import get_llm
from src.utils.logger_conf import logger
from src.utils.decorators import singleton
from langchain_core.messages import SystemMessage, HumanMessage

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


class Filename(BaseModel):
    filename: str | None


@singleton
class FilenameAgent:
    def __init__(self):
        self.llm = get_llm("nxchat")

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
            prompt = ChatPromptTemplate.from_messages([system_prompt, user_prompt])

            structured_llm = self.llm.with_structured_output(Filename).with_retry()
            chain = prompt | structured_llm

            response: Filename = await chain.ainvoke({})
            if not response.filename:
                logger.warning("No content returned from LLM response")
                return None

            logger.info(f"Response: {response}")
            filename = response.filename

            return filename if filename else None
        except Exception as e:
            logger.exception(f"Error extracting filename: {str(e)}")
            return None
