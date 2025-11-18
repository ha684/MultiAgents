import textwrap
from typing import List

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.utils.decorators import singleton
from src.utils.logger_conf import logger
from src.utils import format_context_for_response

COMPRESS_PROMPT_TEMPLATE = textwrap.dedent("""\
You are an information extraction specialist. Extract and summarize key facts from documents that relate to the query.

**Your task:** Present ONLY the information found in the documents, organized clearly with citations.

**Citation format:**
- Each document has: [CITATION: N] and a Source URL
- Extract a SHORT identifier from the source (domain name, key slug, or doc ID)
- Cite using: ([identifier][N]) after each fact
- Example: "Revenue was $50M ([globenewswire][5])"
- Example: "Market grows ([annual-report-2024][1])"
- Multiple sources: "Revenue increased ([source1][1])([source2][3])"
- Keep identifiers SHORT (1-3 words, lowercase, hyphens for spaces)

**How to extract information:**
1. Read the query and identify what information is being requested
2. Extract facts from documents that answer ANY part of the query
3. Include specific details: numbers, dates, names, technical terms
4. Group related facts under descriptive headers
5. Use bullet points for each distinct fact
6. Cite every fact immediately after the statement using ([identifier][N])

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
- Bullet points with citations in format ([identifier][N])
- No commentary about missing information

**Example of what NOT to do:**
 "Environmental constraints are not mentioned in the documents ([doc1][1])([doc2][2])"
 "While the documents do not explicitly cover X, they do mention Y ([report][3])"

**Example of what TO do:**
 "AI adoption in mining will reach 60% by 2025 ([mckinsey][1])"
 "Market growth projected at 39.2% CAGR ([reuters][2])"
 "Revenue increased 15% year-over-year ([q4-earnings][3])"
""")


@singleton
class CompressAgent(BaseAgent):
    """Agent responsible for compressing and organizing information from filtered documents."""

    def __init__(self):
        super().__init__()
        logger.info("Compress Agent initialized successfully.")

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
            formatted_docs = format_context_for_response(reference)
            system_prompt = SystemMessage(content=COMPRESS_PROMPT_TEMPLATE)
            user_content = HumanMessage(
                content=f"""
                Context: \n{formatted_docs}\n\n User Query: {query}
                """
            )
            messages: List[BaseMessage] = [system_prompt, user_content]
            response = await self.simple_llm_call(messages=messages)
            return response.content
        except Exception as e:
            logger.error(f"Error compressing information: {e}", exc_info=True)
            return fallback
