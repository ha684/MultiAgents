from typing import List, cast
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from src.llm.factory import get_llm
from src.models.reference import CitationIndexes
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from src.utils.logger_conf import logger
from src.utils.decorators import singleton

CITATION_PROMPT_TEMPLATE = """
<instructions>
You are a citation expert. Your task is to identify which documents from the provided context contain information that could help answer the user query based on the ENTIRE conversation history.

**CRITICAL ANALYSIS STEPS:**
1. **Analyze the conversation history** - Look at the full context of what the user is asking across all messages
2. **Determine query type** - Is this asking about:
   - Direct information (what IS mentioned/exists)
   - Absence/negative information (what is NOT mentioned/doesn't exist)
   - General conversation (greetings, clarifications, etc.)
3. **Apply appropriate strictness level** based on query complexity and type

**RELEVANCE CRITERIA BY QUERY TYPE:**

**For Direct Queries** (asking about specific facts, data, processes):
- STRICT: Only include documents that directly contain the requested information
- Documents must have clear relevance to the specific entities, topics, or data points mentioned
- Avoid tangentially related documents

**For Absence/Negative Queries** (asking what is NOT mentioned, which entities have NOT experienced something):
- COMPREHENSIVE: Include documents that help establish both what IS and IS NOT covered
- Include documents containing:
  - The specific entities/topics in question (even if they don't mention the negative aspect)
  - Related categories or similar entities for comparison
  - Contextual information that helps establish scope and coverage
  - Documents from relevant timeframes mentioned in the query

**For Conversational/General Queries** (greetings, clarifications, non-specific questions):
- MINIMAL: Only include documents if they are directly relevant to any specific topic mentioned
- For pure conversational queries like "hello", "thank you", return empty indexes
- For clarification requests, focus only on the specific topic being clarified

**CONVERSATION CONTEXT CONSIDERATION:**
- If the current query builds on previous messages, consider the accumulated context
- If the current query is a follow-up (using "it", "that", "also", etc.), identify what it refers to from history
- If the current query changes topic completely, focus on the new topic with appropriate strictness
</instructions>

<analysis_approach>
**Step-by-step analysis process:**

1. **Query Classification:**
   - Is this a greeting/conversational query? → Use MINIMAL approach
   - Is this asking for direct information? → Use STRICT approach  
   - Is this asking about absences/negatives? → Use COMPREHENSIVE approach
   - Is this a follow-up to previous messages? → Consider full conversation context

2. **Relevance Assessment:**
   - For STRICT: Document must contain specific information to answer the query
   - For COMPREHENSIVE: Document must contain entities/topics that help establish presence or absence
   - For MINIMAL: Document must be directly relevant to any specific topic mentioned

3. **Quality Control:**
   - Always prefer precision over recall for conversational queries
   - Always prefer recall over precision for absence/negative queries
   - Balance precision and recall for direct information queries

</analysis_approach>

<output_format>
Return your response as a JSON object with a single key "indexes" containing an array of integers representing the document indexes that are relevant.

Examples:
- If documents 1, 3, and 5 are relevant: {"indexes": [1, 3, 5]}
- If no documents are relevant: {"indexes": []}
- If only document 2 is relevant: {"indexes": [2]}
</output_format>

<examples>
**Example 1 - Absence Query (COMPREHENSIVE approach):**
Query: "List companies that have NOT experienced any security incidents in the past 3 years"
Relevant documents:
- Documents mentioning any companies and their security status
- Documents about security incidents (to establish which companies ARE affected)
- Company directories or lists from relevant sectors
- Security reports from the specified timeframe

**Example 2 - Direct Query (STRICT approach):**
Query: "What is the revenue for Q2 2023?"
Relevant documents:
- Documents containing Q2 2023 financial data
- Revenue reports specifically for Q2 2023
- NOT: General company information, other quarters, or unrelated financial data

**Example 3 - Conversational Query (MINIMAL approach):**
Query: "Hello" or "Thank you"
Relevant documents: {"indexes": []}

**Example 4 - Follow-up Query (Context-aware):**
Previous: "Tell me about Company A's performance"
Current: "What about their security incidents?"
Relevant documents: Documents about Company A's security incidents (combining context from history)
</examples>

**QUALITY ASSURANCE CHECKLIST:**
- Have I classified the query type correctly?
- Am I applying the right strictness level?
- Have I considered the full conversation history?
- Will these documents enable a complete and accurate answer?
- Have I avoided including clearly irrelevant documents?
- Is the context size reasonable (prefer quality over quantity)?
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
        if not documents:
            return "<documents>No relevant documents found.</documents>"

        xml_output = "<documents>\n"

        for i, doc in enumerate(documents):
            xml_output += f'<document index="{i + 1}">\n'
            metadata = getattr(doc, "metadata", {})
            source = metadata.get("original_filename", f"Document {i + 1}")
            folder_path = metadata.get("folder_path", "")
            sheet_name = metadata.get("sheet_name", "N/A")
            xml_output += f"<source>{source}</source>\n"
            if folder_path:
                xml_output += f"<folder_path>{folder_path}</folder_path>\n"
            if sheet_name and sheet_name != "N/A":
                xml_output += f"<sheet_name>{sheet_name}</sheet_name>\n"
            content = getattr(doc, "page_content", "")
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
        formatted_context = self._format_context_for_response(reference)
        if formatted_context == "<documents>No relevant documents found.</documents>":
            logger.info("No relevant documents found")
        formatted_context = self._format_context_for_response(reference)
        if formatted_context == "<documents>No relevant documents found.</documents>":
            logger.info("No relevant documents found")
            return CitationIndexes(indexes=[])

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
