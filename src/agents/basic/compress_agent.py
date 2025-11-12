import textwrap
from typing import List

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.utils.decorators import singleton
from src.utils.logger_conf import logger

COMPRESS_PROMPT_TEMPLATE = textwrap.dedent("""\
You are an information extraction and summarization specialist. Your task is to extract and summarize key facts from documents that are relevant to the query.

**Your job:** Extract relevant information from the documents and present it clearly with proper citations.

**Citation format:**
- Each document has: [CITATION: N]
- Cite using: [N] after each fact
- Example: "Revenue was $50M [5]"
- Multiple sources: "Revenue increased [1], [3]"

**Rules:**
1. Extract ONLY facts that directly relate to the query
2. Keep facts specific: include numbers, dates, names, technical details
3. Cite every fact using [N] format immediately after the statement
4. Group related facts under clear topic headers
5. Use bullet points for clarity
6. Summarize information concisely while preserving ALL key details

**Critical - What NOT to do:**
- DO NOT mention what is missing or not covered in the documents
- DO NOT add statements like "The documents do not mention..." or "No information about..."
- DO NOT include analysis, interpretation, or speculation beyond the documents
- DO NOT add conclusions about gaps in information
- If the query asks about something not in the documents, simply omit that part

**Focus:** Present only what IS in the documents, organized clearly and cited properly.
""")


@singleton
class CompressAgent(BaseAgent):
    """Agent responsible for compressing and organizing information from filtered documents."""

    def __init__(self):
        super().__init__()
        logger.info("Compress Agent initialized successfully.")

    def _format_context_for_response(self, documents: List[Document]) -> str:
        """Formats documents for the response prompt."""
        xml_output = "<documents>\n"
        for i, doc in enumerate(documents):
            content = doc.page_content
            xml_output += f'<document index="{i + 1}">\n'
            xml_output += "<document_content>\n"
            xml_output += f"{content}\n"
            xml_output += "</document_content>\n"
            xml_output += "</document>\n"
        xml_output += "</documents>"
        return xml_output

    async def ainvoke(self, query: str, reference: List[Document]) -> str:
        """
        Compresses information from relevant documents (simple mode).

        Args:
            query: The search query that was used
            reference: All retrieved documents

        Returns:
            Compressed information as a formatted string
        """
        if not reference:
            logger.warning("No relevant documents to compress")
            return ""

        fallback = "\n\n".join([doc.page_content for doc in reference])

        try:
            formatted_docs = self._format_context_for_response(reference)

            system_prompt = SystemMessage(content=COMPRESS_PROMPT_TEMPLATE)
            user_content = HumanMessage(
                content=f"""
                Context: \n{formatted_docs}\n\n User Query: {query}
                Extract relevant facts from these documents. Only include information that is explicitly stated in the documents.
                """
            )
            messages: List[BaseMessage] = [system_prompt, user_content]
            response = await self.simple_llm_call(messages=messages)
            return response.content
        except Exception as e:
            logger.error(f"Error compressing information: {e}", exc_info=True)
            return fallback
