# src/agents/basic/compress_agent.py
import textwrap

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.core.config.llm_config import LLMModelConfigs
from src.core.config.settings import settings
from src.utils.decorators import singleton
from src.utils.logger_conf import logger

COMPRESS_PROMPT_TEMPLATE = textwrap.dedent(
    """\
You are an information extraction specialist. Extract and summarize key facts from documents that relate to the query.

**Your task:** Present ONLY the information found in the documents, organized clearly with citations.

**Citation format:**
- Each document has: [CITATION: N]
- For EACH document, create a SHORT identifier (1-3 words) based on the document's main topic or content
- Cite using: ([identifier][N]) after each fact
- Identifiers should be: lowercase, hyphenated, descriptive
- Example identifiers: "quarterly-earnings", "market-report", "ceo-interview", "tech-specs"
- Example citation: "Revenue was $50M ([earnings-q4][2])"
- Multiple sources: "Market grows ([mckinsey][1])([reuters][3])"

**How to create identifiers:**
- Read the document content first
- Extract the main topic or document type
- Create 1-3 word identifier that describes it
- Use consistent identifiers for the same document throughout your response

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
"""
)


@singleton
class CompressAgent(BaseAgent):
    """Agent responsible for compressing and organizing information from filtered documents."""

    def __init__(self):
        super().__init__(
            provider="nxchat",
            config=LLMModelConfigs(
                model="nxchat-internal",
                base_url=settings.ntqai_base_url,
                api_key=settings.ntqai_api_key,
                temperature=0.5,
            ),
        )
        logger.info("Compress Agent initialized successfully.")

    async def ainvoke(self, query: str, reference: list[Document]) -> str:
        if not reference:
            logger.warning("No relevant documents to compress")
            return ""

        fallback = "\n\n".join([doc.page_content for doc in reference])

        try:
            parts = ["# Retrieved documents:\n"]
            for doc in reference:
                parts.append(f"{doc.page_content}\n")
            formatted_docs = "\n".join(parts)

            messages: list[BaseMessage] = [
                SystemMessage(content=COMPRESS_PROMPT_TEMPLATE),
                AIMessage(content=formatted_docs),
                HumanMessage(content=f"User query: {query}"),
            ]

            response = await self.simple_llm_call(messages=messages)
            return response.content

        except Exception as e:
            logger.error(f"Error compressing information: {e}", exc_info=True)
            return fallback
