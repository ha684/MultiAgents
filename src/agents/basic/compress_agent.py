import textwrap
from typing import List

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.utils.decorators import singleton
from src.utils.logger_conf import logger

COMPRESS_PROMPT_TEMPLATE = textwrap.dedent("""\
You are an information extraction specialist. Extract and summarize key facts from documents that relate to the query.

**Your task:** Present ONLY the information found in the documents, organized clearly with citations.

**Citation format:**
- Each document has: [CITATION: source_name N]
- Cite using: ([source_name][N]) after each fact
- Example: "Revenue was $50M ([annual_report][5])"
- Multiple sources: "Revenue increased ([Q1_report][1])([financial_summary][3])"

**How to extract information:**
1. Read the query and identify what information is being requested
2. Extract facts from documents that answer ANY part of the query
3. Include specific details: numbers, dates, names, technical terms
4. Group related facts under descriptive headers
5. Use bullet points for each distinct fact
6. Cite every fact immediately after the statement using ([source_name][N])

**CRITICAL RULES - YOU MUST FOLLOW THESE:**
- Present ONLY facts that exist in the documents
- If information is not in the documents, DO NOT mention it at all
- NEVER write statements like:
  * "The documents do not mention..."
  * "No specific information about..."
  * "While not explicitly mentioned..."
  * "The documents do not detail..."
- If a query asks about X, Y, and Z, but documents only cover X and Y, only present X and Y
- Skip any part of the query that has no supporting information in the documents

**Your output should contain:**
- Only factual statements found in the documents
- Clear topic headers (when helpful)
- Bullet points with citations in format ([source_name][N])
- No commentary about missing information

**Example of what NOT to do:**
 "Environmental constraints are not mentioned in the documents ([doc1][1])([doc2][2])"
 "While the documents do not explicitly cover X, they do mention Y ([report][3])"

**Example of what TO do:**
 "AI adoption in mining will reach 60% by 2025 ([industry_report][1])"
 "Market growth projected at 39.2% CAGR ([market_analysis][2])"
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
