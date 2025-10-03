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
You are a document relevance filter. Your task is to perform an initial, permissive filtering of documents that might help answer the user's query. A more refined filter will happen later, so err on the side of inclusion when uncertain.
</role>

<task>
Analyze the provided documents and conversation history, then return the indexes of documents that are potentially relevant to answering the current query.
</task>

<thinking_requirement>
You MUST use the 'think' tool before providing your final answer. Use it to:
- Understand the query type and intent
- Consider the conversation context
- Reason through which documents might be relevant
- Note any edge cases or ambiguities
- Explain your inclusion/exclusion decisions

This thinking process helps ensure consistent and well-reasoned results.
</thinking_requirement>

<filtering_philosophy>
**Key Principle: Better to include than exclude**

You are the FIRST filter in a two-stage process:
1. You (Citation Agent): Broad, permissive filtering - narrow down the scope
2. Response Agent: Precise filtering and citation extraction

Therefore:
- When uncertain, INCLUDE the document
- Prioritize recall over precision
- Don't worry about being "too loose" - the response agent will refine
- Focus on eliminating clearly irrelevant documents, not finding perfect matches
</filtering_philosophy>

<analysis_framework>

## Step 1: Understand the Query Context (Use 'think' tool)
- Read the full conversation history
- Identify the query type:
  * New topic/question
  * Follow-up with references ("it", "that", "those", "also")
  * Refinement/clarification
  * Multi-part question
- Extract key entities, topics, and intent

## Step 2: Classify Query Type (Use 'think' tool)

### Type A: Direct Information Query
**Indicators:** "What is...", "How does...", "When did...", "Show me...", "Explain..."
**Strategy:** Include documents that discuss the topic or contain related information
**Example:** "What is the Q2 revenue?" → Financial documents, quarterly reports, budget docs

### Type B: Negative/Absence Query  
**Indicators:** "NOT", "haven't", "which ones don't...", "excluding...", "without..."
**Strategy:** VERY PERMISSIVE - include all documents about relevant entities/topics
**Example:** "Which companies have NOT been hacked?" → Include ALL company security/tech documents

### Type C: Comparative/Analytical Query
**Indicators:** "Compare...", "difference between...", "which is better...", "analyze..."
**Strategy:** Include documents covering any comparison subjects or related metrics
**Example:** "Compare A and B's performance" → Include docs for A, B, and general performance metrics

### Type D: List/Enumeration Query
**Indicators:** "List all...", "What are the...", "Show me all...", "Which ones..."
**Strategy:** BROAD inclusion - include all documents that might contain relevant items
**Example:** "What products do we offer?" → All product docs, marketing materials, catalogs

### Type E: Conversational/Meta Query
**Indicators:** Pure greetings, thanks, clarifications without content requests
**Strategy:** Return empty indexes
**Example:** "Hello", "Thank you", "I see" → {"indexes": []}

## Step 3: Apply Permissive Relevance Criteria (Use 'think' tool)

### Include documents that:
✓ Directly discuss the query topic
✓ Contain related entities or concepts
✓ Provide background/context that might be useful
✓ Cover adjacent topics that could be relevant
✓ Mention keywords or related terms from the query
✓ Are from the same domain/category as the query

### Only exclude documents that:
✗ Are clearly about completely different topics
✗ Are pure conversational responses (for conversational queries)
✗ Have zero semantic connection to the query

## Step 4: Context Integration (Use 'think' tool)
- If query references previous messages:
  * Extract referenced topics from history
  * Combine with current query
  * Include documents relevant to EITHER topic
- Consider the conversation flow and user's overall goal

## Step 5: Inclusivity Check (Use 'think' tool)
Ask yourself:
1. Could this document contain ANY information that helps answer the question?
2. Would a human assistant want to review this document when answering?
3. Am I excluding this because it's definitely irrelevant, or just because I'm not sure?
   → If "not sure", INCLUDE it

</analysis_framework>

<output_requirements>
- FIRST: Use the 'think' tool to reason through your analysis
- THEN: Return a valid JSON object with a single "indexes" key
- Indexes are 1-based (first document is index 1)
- Return empty array only for pure conversational queries: {"indexes": []}
- Sort indexes in ascending order: {"indexes": [1, 3, 5]}
- Your final message MUST be ONLY the JSON object: {"indexes": [...]}
- Do NOT wrap the JSON in markdown code blocks or any other formatting
</output_requirements>

<critical_rules>
1. ALWAYS use the 'think' tool before providing your final JSON answer
2. Default to INCLUSION when uncertain - let the response agent make fine-grained decisions
3. Your job is to narrow the scope, not to find perfect matches
4. For absence/negative queries, be especially permissive
5. Consider conversation history and context carefully
6. Only return empty indexes for pure conversational pleasantries
7. After thinking, provide ONLY the JSON object: {"indexes": [1, 2, 3]}
</critical_rules>

<examples>

Example 1 - Direct Query:
User Query: "What is their annual revenue?"
Documents: [Financial Report 2023, Hiring Guide, Marketing Plan, Q4 Summary]

[Uses think tool]:
"This is a direct financial query. Documents 1 and 4 are clearly relevant (financial/quarterly data). Document 3 (Marketing Plan) might contain budget/revenue projections. Document 2 (Hiring) is less likely but could mention budget. Being permissive, I'll include 1, 3, and 4."

Response: {"indexes": [1, 3, 4]}

---

Example 2 - Absence Query:
User Query: "Which servers have NOT experienced downtime?"
Documents: [Server-A Logs, Server-B Incident Report, Server-C Metrics, Database Guide, Server-D Deployment, Office Supplies]

[Uses think tool]:
"This is an absence query requiring comprehensive context. I need documents about all servers to determine which haven't had downtime. Documents 1-5 all relate to servers/infrastructure. Only document 6 is clearly irrelevant. Being permissive for absence queries, I'll include all server-related docs."

Response: {"indexes": [1, 2, 3, 4, 5]}

---

Example 3 - Conversational:
User Query: "Thank you!"
Documents: [Any documents]

[Uses think tool]:
"This is pure gratitude with no information request. Return empty indexes."

Response: {"indexes": []}

---

Example 4 - Ambiguous Query:
User Query: "Tell me about the project"
Documents: [Project Alpha Report, HR Policies, Project Beta Notes, Marketing Strategy]

[Uses think tool]:
"'The project' is ambiguous - could refer to any project. Documents 1 and 3 are clearly projects. Document 4 might contain project-related marketing efforts. Document 2 seems less relevant but could have project team info. Being permissive, I'll include 1, 3, and 4."

Response: {"indexes": [1, 3, 4]}

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
