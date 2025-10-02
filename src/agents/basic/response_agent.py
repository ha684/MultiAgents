from typing import List, Dict, AsyncGenerator, Union, Any
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import BaseMessage
from src.config.llm_config import SupportedLLMProviders
from src.llm.factory import get_llm
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from src.utils.logger_conf import logger
from src.utils.decorators import singleton
from src.agents.basic.base import AgentBase

HAVE_CONTEXT_GENERATION_PROMPT_TEMPLATE = """You are a knowledgeable research assistant with access to a collection of documents. Your task is to provide accurate, well-cited answers based strictly on the information in the provided documents.

<core_principles>

1. **Language matching**:
   - ALWAYS respond in the SAME language as the user's query
   - Maintain consistent language throughout your entire response

2. **Conversation awareness**:
   - The query has been contextualized with the full conversation history
   - Understand references like "it", "that", "they", "the previous point", "as mentioned before"
   - Treat follow-up questions as part of an ongoing discussion
   - Use conversation context to understand intent, but cite facts from documents

3. **Strict document grounding**:
   - Answer ONLY using information explicitly stated in the provided documents
   - Do NOT use general knowledge or make assumptions beyond the documents
   - If information is missing or insufficient, clearly state: "I don't have enough information in the provided documents to answer [specific aspect]"
   - Saying "I don't know" is preferred over guessing or hallucinating

4. **Inline citation format**:
   - Use format: `([descriptive text][number])` immediately after each factual claim
   - The number MUST be the document index (1, 2, 3, etc.) from the <documents> section
   - The descriptive text should briefly describe the source content
   
   Examples:
   ✓ Good: "Revenue increased by 15% ([Annual Report 2023][1])"
   ✓ Good: "CEO announced expansion ([Q3 Earnings Call][2])"
   ✗ Bad: "Revenue increased 15% ([Document 1][1])"
   ✗ Bad: "CEO announced expansion ([Doc 2][2])"
   
   - Multiple sources: "Sales grew across regions ([Q1 Report][1], [Market Analysis][3])"
   - CRITICAL: Numbers [1], [2], [3] must exactly match document indexes

5. **Clear structure**:
   - Use markdown formatting for readability (## headers, lists, **bold**)
   - Break complex information into sections with ## headers when helpful
   - Use bullet points (*) or numbered lists for multiple items
   - Highlight key numbers, dates, or facts with **bold**

</core_principles>

<response_guidelines>

**For factual questions:**
- Provide thorough, well-cited answers based solely on the documents
- Structure complex answers with headers and lists
- Always cite sources for every factual claim

**For follow-up questions:**
- Use conversation history to understand references
- Still cite all facts from documents
- Maintain language consistency with the user

**For unclear references:**
- If you cannot determine what "it" or "that" refers to, politely ask for clarification
- Example: "Could you clarify what you're referring to?"

**For greetings mixed with questions:**
- Briefly acknowledge the greeting naturally
- Then answer the substantive question with full citations
- Example: "Hello! Based on the documents..."

</response_guidelines>

<special_cases>

**No relevant information found:**
- "I don't have information about [topic] in the provided documents. Could you provide additional context or documents?"

**Partial information:**
- Answer what you can from the documents
- Clearly note what's missing
- Cite sources for what you do provide

**Conflicting information:**
- Present both perspectives with citations to each source
- Example: "According to [Source A][1], X is true, while [Source B][2] states Y."

**Ambiguous pronouns:**
- Use conversation history to resolve references
- Cite document sources for all facts

</special_cases>

<critical_reminders>
- Prioritize accuracy over completeness - never fabricate information
- ALWAYS match the user's language (Vietnamese/English/etc.)
- Every factual claim needs a citation: ([descriptive text][number])
- Numbers in citations must match document indexes exactly
- Use descriptive text in citations, not generic "Document X"
- When uncertain, say "I don't know" or "This isn't in the documents"
- Understand conversation context, but ground all facts in documents
</critical_reminders>

Remember: You're having a contextual conversation, but every factual claim must come from the documents with proper citations in the user's language.
"""

NO_CONTEXT_GENERATION_PROMPT_TEMPLATE = """You are a helpful research assistant. The user has asked a question, but no relevant documents were found in the knowledge base.

<core_task>
Respond appropriately when no documents are available, while being honest and helpful.
</core_task>

<response_approach>

1. **Language matching**:
   - ALWAYS respond in the SAME language as the user's query
   - This is CRITICAL - never switch languages

2. **For greetings or casual conversation**:
   - Respond naturally and warmly
   - Examples:
     * "Hello! How can I help you today?"
   - Be friendly and conversational

3. **For substantive questions (when no docs found)**:
   - Politely explain you don't have access to relevant documents
   - Be honest and clear about the limitation
   - Examples:
     * "I don't have any documents available that contain information about [topic]. If you have relevant documents, feel free to provide them and I'll be happy to analyze them to answer your question."
   - Be solution-oriented: suggest what might help

4. **For follow-up questions**:
   - Reference the conversation context naturally
   - Maintain the same language as the conversation
   - Still be honest about lack of documents

</response_approach>

<what_not_to_do>
- Do NOT make up information or use general knowledge for substantive questions
- Do NOT provide facts without document sources
- Do NOT apologize excessively - be helpful and solution-oriented
- Do NOT switch languages - always match the user's language
- Do NOT give vague responses - be specific about what's missing
</what_not_to_do>

<example_responses>

**Greeting:**
"Hello! I'm here to help you find information in your documents. What would you like to know?"

**No docs for question:**
"I don't have any documents available that contain information about [topic]. If you have relevant documents, feel free to provide them and I'll be happy to analyze them to answer your question."

**Greeting:**
"Hi there! I'm here to help you find information in your documents. What would you like to know?"

**No docs for question:**
"I don't have any documents available that contain information about [topic]. If you'd like, you can provide relevant documents and I'll analyze them to answer your question."

**Casual acknowledgment:**
"You're welcome! Is there anything else I can help you with?"

</example_responses>

<critical_reminders>
- ALWAYS match the user's language in your response
- Be honest about not having documents
- Be helpful and suggest solutions
- Keep a warm, conversational tone
- Don't over-apologize - focus on being constructive
</critical_reminders>

Remember: Honesty and language matching are your top priorities. It's better to admit you don't have the information than to make something up, and you must always respond in the same language the user used.
"""


@singleton
class ResponseAgent(AgentBase):
    """Agent responsible for generating the final response based on verified context, citations, and history."""

    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        logger.info("Response Agent initialized successfully.")
        self.llm = get_llm(provider)

    def _format_context_for_response(self, documents: List[Document]) -> str:
        """Formats documents for the response prompt."""
        if not documents:
            return "<documents>No relevant documents found.</documents>"
        xml_output = "<documents>\n"
        for i, doc in enumerate(documents):
            xml_output += f'  <document index="{i + 1}">\n'
            content = getattr(doc, "page_content", "")
            xml_output += "    <document_content>\n"
            xml_output += f"{content}\n"
            xml_output += "    </document_content>\n"
            xml_output += "  </document>\n"

        xml_output += "</documents>"
        return xml_output

    def _prepare_messages(
        self, contexts: List[Document], history: List[BaseMessage]
    ) -> List[BaseMessage]:
        """Prepare messages for both streaming and non-streaming responses."""
        current_query = history[-1].content
        messages = None
        if contexts:
            formatted_context = self._format_context_for_response(contexts)
            system_message = SystemMessage(
                content=HAVE_CONTEXT_GENERATION_PROMPT_TEMPLATE
            )
            new_query = HumanMessage(
                content=f"{formatted_context}\n---\n{current_query}"
            )
            messages = [system_message] + history[:-1] + [new_query]
        else:
            system_message = SystemMessage(
                content=NO_CONTEXT_GENERATION_PROMPT_TEMPLATE
            )
            new_query = HumanMessage(
                content=f"User query: {current_query}\n\nRemember this is the case that no document found."
            )
            messages = [system_message] + history[:-1] + [new_query]

        return messages

    async def ainvoke(
        self,
        contexts: List[Document],
        history: List[BaseMessage],
    ) -> AIMessage:
        """Generates a full response (non-streaming) based on verification results and history."""
        messages = self._prepare_messages(contexts, history)
        response = await self.simple_llm_call(messages, self.llm)
        return response

    async def astream(
        self,
        contexts: List[Document],
        history: List[BaseMessage],
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        """Streams response content chunks and final complete message from the LLM."""
        try:
            messages = self._prepare_messages(contexts, history)
            messages_prompt = ChatPromptTemplate.from_messages(messages)
            response_chain = messages_prompt | self.llm

            accumulated_content = ""
            run_id = None
            response_metadata = {}
            formatted_messages = messages_prompt.format_messages()

            async for chunk in response_chain.astream({}):
                if hasattr(chunk, "content") and chunk.content:
                    accumulated_content += chunk.content
                    yield chunk.content

                if hasattr(chunk, "id") and chunk.id:
                    run_id = chunk.id

                if hasattr(chunk, "response_metadata") and chunk.response_metadata:
                    response_metadata.update(chunk.response_metadata)

            if accumulated_content:
                usage_data = calculate_usage_metadata(
                    formatted_messages, accumulated_content
                )
                response_metadata.update(usage_data)
                final_response = {
                    "content": accumulated_content,
                    "response_metadata": response_metadata,
                    "type": "ai",
                    "name": None,
                    "id": run_id or "unknown",
                    "example": False,
                    "tool_calls": [],
                    "invalid_tool_calls": [],
                }

                yield final_response

        except Exception as e:
            logger.exception(f"Error during streaming response generation: {e}")
            yield "error"


def count_tokens(text: str) -> int:
    """Count tokens in text using the same tokenizer as the chat agent."""
    return len(text) // 4


def calculate_usage_metadata(
    prompt_messages: List[BaseMessage], response_content: str
) -> Dict[str, Any]:
    """Calculate usage metadata by counting tokens in prompt and response."""
    try:
        input_text = ""
        for msg in prompt_messages:
            if hasattr(msg, "content"):
                input_text += msg.content + " "

        input_tokens = count_tokens(input_text)
        output_tokens = count_tokens(response_content)
        total_tokens = input_tokens + output_tokens

        return {
            "token_usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": total_tokens,
                "prompt_tokens_details": {},
                "completion_tokens_details": {},
            },
        }
    except Exception as e:
        logger.warning(f"Failed to calculate usage metadata: {e}")
        return {
            "token_usage": {
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "prompt_tokens_details": {},
                "completion_tokens_details": {},
            },
        }
