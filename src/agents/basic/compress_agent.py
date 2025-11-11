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
- Cite using: [N]
- Example: "Revenue was $50M [5]"

**Rules:**
1. Only extract facts that directly answer or relate to the query
2. Keep facts specific: include numbers, dates, names
3. Cite every fact using [N] format
4. If the same fact appears in multiple documents, cite all: [1], [3]
5. Group related facts under simple topic headers when helpful
6. Use bullet points for lists of facts
7. DO NOT invent, infer, or elaborate beyond what the documents say

**Output format:**
```
## [Topic if needed]
- Fact from document [N]
- Another fact [M]
- Fact from multiple sources [N], [M]
```

**What to avoid:**
- Don't add your own analysis or interpretation
- Don't combine facts from different sources unless they say the exact same thing
- Don't include vague or generic statements without specific details
- Don't extract information unrelated to the query
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
