from typing import List, cast
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from src.llm.factory import get_llm
from src.models.reference import CitationIndexes
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from src.utils.logger_conf import logger
from src.utils.decorators import singleton

CITATION_PROMPT_TEMPLATE = """
<role>
You are an expert document relevance evaluator. Your task is to identify which documents contain information that helps answer the user's query within the conversation context.
</role>

<task>
Analyze the provided documents and conversation history, then return ONLY the indexes of documents that are relevant to answering the current query.
</task>

<analysis_framework>

## Step 1: Understand the Query Context
- Read the ENTIRE conversation history to understand the full context
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
</output_requirements>

<critical_rules>
1. NEVER include documents just because they share keywords - require semantic relevance
2. For absence queries, DO include documents that help establish context even without explicit negatives
3. For conversational queries with no information request, return empty indexes
4. When in doubt between including/excluding, consider the query type:
   - Direct queries: EXCLUDE (favor precision)
   - Absence queries: INCLUDE (favor recall)
   - Conversational queries: EXCLUDE (favor minimalism)
5. Always consider the full conversation history before making decisions
</critical_rules>

<examples>

Example 1 - Direct Query:
Conversation History:
- User: "Tell me about Company X"
- Assistant: "Company X is a tech company..."
- User: "What is their annual revenue?"

Documents:
1. Company X overview and mission
2. Company X Q4 2023 financial report with revenue data
3. Company X hiring practices
4. Company Y financial report

Analysis:
- Query type: Direct (asking for specific data)
- Strategy: STRICT
- Relevant: Document 2 (contains revenue data)
Output: {"indexes": [2]}

---

Example 2 - Absence Query:
User Query: "Which servers in the report have NOT experienced downtime in the last 6 months?"

Documents:
1. Server-A monitoring logs showing 99.9% uptime
2. Server-B incident report about downtime in March
3. Server-C performance metrics (no downtime mentioned)
4. Database optimization guide (unrelated)
5. Server-D deployment schedule

Analysis:
- Query type: Negative/Absence
- Strategy: COMPREHENSIVE
- Relevant: 1, 2, 3, 5 (all server docs help establish which have/haven't had downtime)
- Irrelevant: 4 (unrelated topic)
Output: {"indexes": [1, 2, 3, 5]}

---

Example 3 - Follow-up with Context:
Conversation History:
- User: "Show me security incidents for Company A"
- Assistant: "Company A had 2 incidents..."
- User: "What about Company B?"

Documents:
1. Company A security report 2023
2. Company B security report 2023
3. Company B product roadmap
4. Industry security trends

Analysis:
- Query type: Direct follow-up (asking about Company B)
- Context: Previous query was about security incidents
- Strategy: STRICT (direct information about Company B security)
- Relevant: Document 2
Output: {"indexes": [2]}

---

Example 4 - Conversational:
User Query: "Thanks, that's helpful!"

Documents:
1-10. Various technical documents

Analysis:
- Query type: Conversational/Meta
- Strategy: MINIMAL
- No information request detected
Output: {"indexes": []}

---

Example 5 - Comparative Query:
User Query: "Compare the performance of Service A and Service B"

Documents:
1. Service A performance metrics Q1-Q4
2. Service B performance metrics Q1-Q4
3. Service C deployment guide
4. Service A code repository
5. Service B user feedback summary

Analysis:
- Query type: Comparative
- Strategy: BALANCED
- Relevant: 1, 2, 5 (provide comparable performance data)
- Maybe relevant: 4 (less directly about performance)
- Irrelevant: 3 (different service)
Output: {"indexes": [1, 2, 5]}

</examples>

<final_checklist>
Before returning your answer:
✓ I have classified the query type correctly
✓ I have applied the appropriate relevance strategy
✓ I have considered the full conversation history
✓ I have included all necessary documents (recall)
✓ I have excluded clearly irrelevant documents (precision)
✓ My output is valid JSON with sorted indexes
</final_checklist>
"""


@singleton
class CitationAgent:
    """Agent responsible for extracting citations from retrieved documents."""

    def __init__(self):
        self.llm = get_llm("nxchat")
        self.structured_llm = self.llm.with_structured_output(CitationIndexes)
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

    async def extract_citations(
        self, history: List[BaseMessage], reference: List[Document]
    ) -> CitationIndexes:
        """Extracts citations from the provided context based on the user query."""
        if not reference:
            return CitationIndexes(indexes=[])

        formatted_context = self._format_context_for_response(reference)
        system_prompt = SystemMessage(content=CITATION_PROMPT_TEMPLATE)
        user_content = HumanMessage(
            content=f"""Here are documents:\n{formatted_context}\n---\nExtract correct citations for the following query: {history[-1].content}"""
        )
        messages = [system_prompt] + history[:-1] + [user_content]
        citation_prompt = ChatPromptTemplate.from_messages(messages)

        citation_chain = citation_prompt | self.structured_llm
        try:
            response = citation_chain.invoke({})

            return cast(
                CitationIndexes, response
            )  # Ensure the response is of type CitationIndexes
        except Exception as e:
            logger.info(f"Error extracting citations: {e}")
            return CitationIndexes(indexes=[])
