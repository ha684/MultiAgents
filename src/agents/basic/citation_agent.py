from typing import List
from langchain_core.documents import Document
from src.llm.factory import get_llm
from src.models.reference import CitationIndexes
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from src.utils.logger_conf import logger
from src.utils.decorators import singleton
from src.agents.tools.server.mcp_retrieve_tools import think
from src.utils import parse_response
from src.agents.basic.base import AgentBase

CITATION_PROMPT_TEMPLATE = """
<role>
You are an expert document relevance evaluator. Your task is to identify which documents contain information that helps answer the user's query within the conversation context.
</role>

<task>
Analyze the provided documents and conversation history, then return ONLY the indexes of documents that are relevant to answering the current query.
</task>

<optional_thinking>
You have access to a 'think' tool that you MAY use if you need to reason through complex cases. Use it when:
- The query type is ambiguous or complex
- You need to carefully distinguish between similar documents
- The relevance decision requires multi-step reasoning

For straightforward queries where the relevance is clear, you can skip the thinking step and respond directly.
</optional_thinking>

<analysis_framework>

## Step 1: Understand the Query Context
- Read the conversation history to understand the full context
- Identify if the current query is:
  * A new topic/question
  * A follow-up using references ("it", "that", "those", "also", etc.)
  * A refinement or clarification of a previous question
  * A multi-part question requiring multiple information sources

## Step 2: Classify Query Type

### Type A: Direct Information Query
**Indicators:** "What is...", "How does...", "When did...", "Show me...", "Explain..."
**Strategy:** STRICT relevance - only documents directly containing the requested information
**Example:** "What is the Q2 revenue?" → Only Q2 financial documents

### Type B: Negative/Absence Query  
**Indicators:** "NOT", "haven't", "which ones don't...", "excluding...", "without..."
**Strategy:** COMPREHENSIVE relevance - include documents that establish both presence AND absence
**Example:** "Which companies have NOT been hacked?" → Include all company security documents

### Type C: Comparative/Analytical Query
**Indicators:** "Compare...", "difference between...", "which is better...", "analyze..."
**Strategy:** BALANCED relevance - include documents covering all entities being compared
**Example:** "Compare A and B's performance" → Include documents for both A and B

### Type D: Conversational/Meta Query
**Indicators:** Greetings, thanks, clarifications without specific content requests
**Strategy:** MINIMAL relevance - typically return empty indexes
**Example:** "Hello", "Thank you", "I see" → Return {"indexes": []}

## Step 3: Apply Relevance Criteria

### For Direct Queries (STRICT):
✓ Document contains specific facts/data requested
✓ Document discusses the exact entities/topics mentioned
✗ Document only tangentially related
✗ Document about similar but different topics

### For Negative/Absence Queries (COMPREHENSIVE):
✓ Documents mentioning the entities in question (even without the negative aspect)
✓ Documents about related entities for comparison context
✓ Documents from relevant time periods or categories
✓ Documents that help establish what IS covered (to infer what ISN'T)

### For Comparative Queries (BALANCED):
✓ Documents covering any of the comparison subjects
✓ Documents with metrics/data that enable comparison
✗ Documents covering only unrelated entities

### For Conversational Queries (MINIMAL):
✓ Only if there's a specific topic embedded in the conversational phrase
✗ For pure pleasantries or acknowledgments

## Step 4: Context Integration
- If query references previous messages ("as mentioned before", "also", "additionally"):
  * Extract the referenced topic from conversation history
  * Combine with current query requirements
- If query shifts topic completely:
  * Focus solely on new topic
  * Ignore previous conversation context for relevance

## Step 5: Quality Filtering
Before finalizing, ask:
1. Does this document directly help answer the question?
2. For absence queries: Does this document help establish what exists/doesn't exist?
3. Is this the minimal sufficient set? (Avoid over-including)
4. Is this comprehensive enough? (Avoid under-including for absence queries)

</analysis_framework>

<output_requirements>
- Return a valid JSON object with a single "indexes" key
- Indexes are 1-based (first document is index 1)
- Return empty array for irrelevant queries: {"indexes": []}
- Sort indexes in ascending order: {"indexes": [1, 3, 5]}
- Your final message MUST be ONLY the JSON object: {"indexes": [...]}
- Do NOT wrap the JSON in markdown code blocks or any other formatting
</output_requirements>

<critical_rules>
1. You MAY use the 'think' tool if you need to reason through complex cases, but it's optional
2. NEVER include documents just because they share keywords - require semantic relevance
3. For absence queries, DO include documents that help establish context even without explicit negatives
4. For conversational queries with no information request, return empty indexes
5. When in doubt between including/excluding, consider the query type:
   - Direct queries: EXCLUDE (favor precision)
   - Absence queries: INCLUDE (favor recall)
   - Conversational queries: EXCLUDE (favor minimalism)
6. Always consider the full conversation history before making decisions
7. Your FINAL response must be ONLY a JSON object: {"indexes": [1, 2, 3]}
</critical_rules>

<examples>

Example 1 - Direct Query (No Thinking Needed):
User Query: "What is their annual revenue?"
Documents: [Financial Report 2023, Hiring Guide, Marketing Plan]

Direct Response: {"indexes": [1]}

Reasoning: Clear direct query about revenue, and document 1 is obviously the financial report.

---

Example 2 - Complex Absence Query (Thinking Helpful):
User Query: "Which servers have NOT experienced downtime in the last 6 months?"
Documents: [Server-A Logs, Server-B Incident Report, Server-C Metrics, Database Guide, Server-D Deployment]

[Uses think tool to reason through which documents help establish presence/absence]

Final Response: {"indexes": [1, 2, 3, 5]}

---

Example 3 - Simple Conversational (No Thinking Needed):
User Query: "Thank you!"
Documents: [Any documents]

Direct Response: {"indexes": []}

Reasoning: Pure pleasantry with no information request.

</examples>
"""


@singleton
class CitationAgent(AgentBase):
    """Agent responsible for extracting citations from retrieved documents."""

    def __init__(self):
        self.llm = get_llm("nxchat")
        self.llm_with_tools = self.llm.bind_tools([think])
        self.max_iterations = 10
        logger.info("Citation Agent initialized successfully.")

    def _format_context_for_response(self, documents: List[Document]) -> str:
        """Formats documents for the response prompt."""
        xml_output = "<documents>\n"
        for i, doc in enumerate(documents):
            xml_output += f'<document index="{i + 1}">\n'
            content = doc.page_content
            xml_output += "<document_content>\n"
            xml_output += f"{content}\n"
            xml_output += "</document_content>\n"
            xml_output += "</document>\n"
        xml_output += "</documents>"
        return xml_output

    async def ainvoke(
        self, history: List[BaseMessage], reference: List[Document]
    ) -> CitationIndexes:
        """Extracts citations from the provided context based on the user query."""
        if not reference:
            return CitationIndexes(indexes=[])

        try:
            formatted_context = self._format_context_for_response(reference)
            system_prompt = SystemMessage(content=CITATION_PROMPT_TEMPLATE)
            user_content = HumanMessage(
                content=f"""Here are documents:\n{formatted_context}\n---\nExtract correct citations for the following query: {history[-1].content}"""
            )
            messages: List[BaseMessage] = (
                [system_prompt] + history[:-1] + [user_content]
            )

            response = await self.iterative_llm_call_structured(
                messages=messages,
                llm_with_tools=self.llm_with_tools,
                available_tools={"think": think},
                max_iterations=self.max_iterations,
                parse_fn=parse_response,
                retry_prompt='Please provide your final answer as a JSON object with the exact format: {"indexes": [1, 2, 3]}',
            )
            return CitationIndexes(indexes=response.content["indexes"])

        except Exception as e:
            logger.error(f"Error extracting citations: {e}", exc_info=True)
            return CitationIndexes(indexes=[])
