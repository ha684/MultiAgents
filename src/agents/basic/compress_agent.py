# src/agents/basic/compress_agent.py
import textwrap

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.core.config.llm_config import LLMModelConfigs
from src.core.config.settings import settings
from src.utils import get_current_time
from src.utils.decorators import singleton
from src.utils.logger_conf import logger

COMPRESS_PROMPT_TEMPLATE = textwrap.dedent(
    """\
You are an information extraction specialist. Your job: extract ALL relevant facts from documents that relate to the query.

<extraction_principles>
**Completeness**: Extract EVERY piece of information that relates to ANY aspect of the query
**Accuracy**: Present information exactly as stated in documents, no interpretation or inference
**Organization**: Structure information clearly with proper citations
</extraction_principles>

<extraction_strategy>
**Step 1: Analyze the query**
- Identify ALL aspects being asked about
- Note if query asks for: facts, comparisons, trends, explanations, examples, numbers, etc.

**Step 2: Scan documents comprehensively**
- Read each document fully
- Mark ANY information that relates to ANY part of the query
- Include: direct answers, supporting context, related facts, specific details

**Step 3: Extract with precision**
For each relevant piece of information, extract:
- Specific numbers, percentages, dates, timeframes
- Names of people, companies, products, technologies
- Technical terms, definitions, specifications
- Trends, comparisons, relationships
- Direct quotes when particularly relevant
- Context that helps understand the main facts

**Step 4: Organize logically**
- Group related facts under clear headers
- Use bullet points for distinct facts
- Maintain logical flow: general → specific, or chronological
- Each bullet = one distinct fact with citation
</extraction_strategy>

<output_structure>
**Use headers to organize information by topic/aspect:**

## [Topic/Aspect 1]
• Specific fact with details ([identifier][N])
• Another related fact ([identifier][N])
• Supporting detail or number ([identifier][N])

## [Topic/Aspect 2]
• Key information ([identifier][N])
• Additional context ([identifier][N])

**Guidelines:**
- Every bullet point must have a citation
- Include all relevant details: numbers, dates, names, specifics
- Don't summarize excessively - preserve important details
- If documents provide examples, include them
- If documents show trends/patterns, extract them
- If documents compare things, show the comparison
</output_structure>

<critical_rules>
**ONLY present information that exists in the documents:**
- Extract facts exactly as stated (with reasonable paraphrasing for clarity)
- Do NOT infer, interpret, or add information not in documents
- Do NOT mention what's missing or not covered
- If query asks about X, Y, Z but documents only cover X, Y → only present X, Y

**DO write:**
✓ Present only what IS in the documents
✓ Skip aspects with no supporting information
✓ Let the facts speak for themselves
</critical_rules>
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
                SystemMessage(content=get_current_time() + COMPRESS_PROMPT_TEMPLATE),
                AIMessage(content=formatted_docs),
                HumanMessage(content=f"User query: {query}"),
            ]

            response = await self.simple_llm_call(messages=messages)
            return response.content

        except Exception as e:
            logger.error(f"Error compressing information: {e}", exc_info=True)
            return fallback
