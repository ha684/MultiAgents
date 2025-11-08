import textwrap
from typing import List

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.utils.decorators import singleton
from src.utils.logger_conf import logger

COMPRESS_PROMPT_TEMPLATE = textwrap.dedent("""\
You are an information extraction specialist. Extract key facts from documents that are relevant to the query.

**Your job:** Copy relevant facts from the documents with proper citations. Do NOT add information that isn't in the documents.

**Citation format:**
- Each document has: [CITATION: N]
- Cite using: ([SourceName][N])
- Example: "Revenue was $50M ([Q2 Report][5])"

**Rules:**
1. Only extract facts that directly answer or relate to the query
2. Keep facts specific: include numbers, dates, names
3. Cite every fact using ([SourceName][N]) format
4. If the same fact appears in multiple documents, cite all: ([Source1][1], [Source2][3])
5. Group related facts under simple topic headers when helpful
6. Use bullet points for lists of facts
7. DO NOT invent, infer, or elaborate beyond what the documents say

**Output format:**
```
## [Topic if needed]
- Fact from document ([Source][N])
- Another fact ([Source][M])
- Fact from multiple sources ([Source1][N], Source2][M])
```

**What to avoid:**
- Don't add your own analysis or interpretation
- Don't combine facts from different sources unless they say the exact same thing
- Don't include vague or generic statements without specific details
- Don't extract information unrelated to the query
""")

CONSOLIDATION_COMPRESS_PROMPT = textwrap.dedent("""\
You are a knowledge consolidation specialist. Merge new information with existing knowledge while avoiding duplication.

**Your job:** 
1. Add new facts from new documents to existing knowledge
2. If a fact already exists, add the new citation to it (don't duplicate)
3. Preserve all existing citations
4. Keep the output organized and concise

**Citation rules:**
- Existing knowledge has: ([Source][N])
- New documents have: [CITATION: N]
- When merging, combine citations: ([OldSource][5], [NewSource][18])

**Merge strategy:**

**DUPLICATE** (same fact exists):
```
Before: "Revenue: $50M ([Q2 Report][5])"
New [18]: "Q2 revenue: $50M"
After: "Revenue: $50M ([Q2 Report][5], [Update][18])"
```

**NEW DETAIL** (adds to existing fact):
```
Before: "Revenue: $50M ([Q2 Report][5])"
New [18]: "driven by enterprise sales"
After: "Revenue: $50M, driven by enterprise sales ([Q2 Report][5], [Update][18])"
```

**COMPLETELY NEW**:
```
Before: (no mention of Feature B)
New [25]: "Feature B launches Q3"
After: Add new bullet "Feature B launches Q3 ([Roadmap][25])"
```

**CONTRADICTION**:
```
Before: "Deadline: June 15 ([Memo][2])"
New [30]: "Deadline: June 30"
After: "Deadline: June 15 ([Memo][2]) - NOTE: Conflicting date June 30 in ([Email][30])"
```

**Critical rules:**
1. Never remove existing citations
2. Don't repeat the same fact twice
3. Only add genuinely new information
4. Group related facts together
5. Every fact must have at least one citation
6. Keep output concise - merge aggressively
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
                content=f"""<query>{query}</query>

{formatted_docs}

Extract relevant facts from these documents. Only include information that is explicitly stated in the documents."""
            )
            messages: List[BaseMessage] = [system_prompt, user_content]

            response = await self.simple_llm_call(messages=messages)

            compressed_content = response.content
            return compressed_content

        except Exception as e:
            logger.error(f"Error compressing information: {e}", exc_info=True)
            logger.warning("Using fallback: returning raw document content")
            return fallback

    async def ainvoke_with_merge(
        self, query: str, new_documents: List[Document], existing_knowledge: str
    ) -> str:
        """
        Compress new documents while merging with existing knowledge (consolidation mode).

        This method is more expensive but produces better organized,
        deduplicated knowledge base.

        Args:
            query: The search query context
            new_documents: New documents to process
            existing_knowledge: Previously accumulated knowledge

        Returns:
            Consolidated knowledge as a formatted string
        """
        if not new_documents:
            logger.warning("No new documents to compress")
            return existing_knowledge

        try:
            formatted_docs = self._format_context_for_response(new_documents)

            user_content_text = textwrap.dedent(f"""\
                <query_context>
                Current search query: {query}
                </query_context>

                <existing_knowledge>
                {existing_knowledge}
                </existing_knowledge>

                <new_documents>
                {formatted_docs}
                </new_documents>

                Merge the new documents with existing knowledge. Avoid duplicating facts that already exist.
                """)

            system_prompt = SystemMessage(content=CONSOLIDATION_COMPRESS_PROMPT)
            user_content = HumanMessage(content=user_content_text)
            messages: List[BaseMessage] = [system_prompt, user_content]

            response = await self.simple_llm_call(messages=messages)

            consolidated = response.content
            return consolidated

        except Exception as e:
            logger.error(f"Consolidation failed: {e}", exc_info=True)
            logger.warning("Using fallback: returning existing knowledge")
            return existing_knowledge
