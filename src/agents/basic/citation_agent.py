# src/agents/basic/citation_agent.py

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.agents.tools.server.mcp_retrieve_tools import think
from src.core.config.llm_config import LLMModelConfigs
from src.core.config.settings import settings
from src.domain.schemas.chat import CitationIndexes
from src.utils import format_context_for_response, parse_response
from src.utils.decorators import singleton
from src.utils.logger_conf import logger

CITATION_PROMPT_TEMPLATE = """
<role>
You are a document filter. Identify documents that might help answer the user's query.
Be permissive - when in doubt, include the document. A second filter will refine later.
</role>

<task>
Return indexes of potentially relevant documents as JSON: {"indexes": [1, 2, 3]}
</task>

<thinking_requirement>
MUST use 'think' tool first to:
- Understand the query and context
- Reason which documents might be relevant
- Explain inclusion/exclusion decisions
</thinking_requirement>

<filtering_strategy>

**Key Principle: Better to include than exclude**

You are the FIRST of two filters:
1. You: Broad filtering - eliminate clearly irrelevant documents
2. Response Agent: Precise filtering and citation

**Query Types & Strategies:**

1. **Direct Questions** ("What is X?", "How does Y work?")
   - Include: Documents discussing the topic or related concepts

2. **Negative/Absence Queries** ("Which ones DON'T...", "NOT", "haven't")
   - Be VERY permissive - include ALL documents about relevant entities

3. **Comparisons** ("Compare A vs B", "difference between")
   - Include: Documents about ANY comparison subjects

4. **Lists** ("List all...", "What are the...", "Show me...")
   - Be BROAD - include all documents that might contain items

5. **Conversational Only** ("Hello", "Thank you", "I see")
   - Return: {"indexes": []}

**Include documents that:**
- Discuss the query topic directly or indirectly
- Contain related entities, concepts, or keywords
- Provide useful context or background
- Are from the same domain/category

**Exclude only documents that:**
- Are clearly about completely different topics
- Have zero connection to the query

**Context Integration:**
- If query references previous messages ("it", "that", "also"), extract topics from history
- Include documents relevant to current query OR referenced topics

</filtering_strategy>

<output_format>
1. FIRST: Use 'think' tool to reason through analysis
2. THEN: Return ONLY valid JSON: {"indexes": [1, 3, 5]}
   - 1-based indexes (first document = 1)
   - Sorted ascending order
   - Empty array for conversational queries: {"indexes": []}
   - NO markdown, NO code blocks, ONLY JSON
</output_format>

<examples>
Query: "What is their revenue?"
Docs: [Financial Report, Hiring Guide, Marketing Plan, Q4 Summary]
Think: "Financial query. Docs 1,4 clearly relevant. Doc 3 might have revenue projections. Include 1,3,4."
Output: {"indexes": [1, 3, 4]}

---

Query: "Which servers have NOT had downtime?"
Docs: [Server-A Logs, Server-B Incident, Server-C Metrics, Database Guide, Office Supplies]
Think: "Absence query - need all server docs to determine which lack downtime. Docs 1-4 are server-related. Doc 5 irrelevant."
Output: {"indexes": [1, 2, 3, 4]}

</examples>

<critical_rules>
1. ALWAYS use 'think' tool before JSON output
2. Default to INCLUSION when uncertain
3. Your job: eliminate obvious irrelevants, not find perfect matches
4. For absence/negative queries: be especially permissive
5. Consider conversation history carefully
6. Final output: ONLY JSON object {"indexes": [...]}
</critical_rules>
"""


@singleton
class CitationAgent(BaseAgent):
    """Agent responsible for extracting citations from retrieved documents."""

    def __init__(self):
        super().__init__(
            provider="nxchat",
            config=LLMModelConfigs(
                model="nxchat-internal",
                base_url=settings.ntqai_base_url,
                api_key=settings.ntqai_api_key,
                temperature=0.0,
            ),
        )
        logger.info("Citation Agent initialized successfully.")

    async def ainvoke(self, query: str, reference: list[Document]) -> CitationIndexes:
        """Extracts citations from the provided context based on the user query."""
        if not reference:
            return CitationIndexes(indexes=[])

        try:
            formatted_context = format_context_for_response(reference)

            messages: list[BaseMessage] = [
                SystemMessage(content=CITATION_PROMPT_TEMPLATE),
                AIMessage(content=f"Retrieved documents:\n\n{formatted_context}"),
                HumanMessage(
                    content=f"Extract correct citations for the following query: {query}"
                ),
            ]

            response = await self.iterative_llm_call_structured(
                messages=messages,
                llm_with_tools=self.thinking_llm,
                available_tools={"think": think},
                max_iterations=10,
                parse_fn=parse_citation_response,
                retry_prompt='Please provide your final answer as a JSON object with the exact format: {"indexes": [1, 2, 3]}',
            )
            logger.info(f"Citation response: {response}")
            return CitationIndexes(indexes=response["indexes"])

        except Exception as e:
            logger.error(f"Error extracting citations: {e}", exc_info=True)
            return CitationIndexes(indexes=[])


def parse_citation_response(content: str) -> CitationIndexes:
    """Parse citation response from content"""
    try:
        parsed = parse_response(content)
        if parsed is None:
            return None
        return parsed
    except Exception as e:
        logger.error(f"Error parsing citation response: {e}")
        return None
