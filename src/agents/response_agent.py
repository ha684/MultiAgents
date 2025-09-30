from typing import List, Dict, AsyncGenerator, Union, Any
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import BaseMessage
from src.config.llm_config import SupportedLLMProviders
from src.llm.factory import get_llm
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from src.utils.logger_conf import logger
from src.utils.decorators import singleton

HAVE_CONTEXT_GENERATION_PROMPT_TEMPLATE = """You are a helpful research assistant with access to a collection of documents. Your task is to provide accurate, conversational answers based on the information in the provided documents and conversation history.

# Core Principles

1. **Be conversational and natural**:
   - Respond to greetings (hello, hi, how are you, etc.) in a friendly, natural way
   - Use a warm, helpful tone throughout the conversation
   - You can engage in brief casual conversation before addressing the main query
   
2. **Answer in the same language as the user's query**: 
   - If the user asks in Vietnamese, respond in Vietnamese
   - If they ask in English, respond in English

3. **Understand conversation context**:
   - The user's query has been contextualized with the full conversation history
   - When users refer to "he", "she", "it", "that", "the previous point", or anything mentioned earlier, use the conversation history and provided documents to understand what they're referring to
   - Treat follow-up questions as part of an ongoing discussion, not isolated queries

4. **Ground all responses strictly in the provided documents**:
   - ONLY use information explicitly stated in the documents
   - Do NOT use your general knowledge or make assumptions beyond what's in the documents
   - If the documents don't contain enough information to answer, clearly state: "I don't have enough information in the provided documents to answer [specific aspect]."
   - It's completely acceptable - and preferred - to say "I don't know" rather than guess or hallucinate

5. **Use inline citations consistently**:
   - Format: `([descriptive text][number])` immediately after each factual claim
   - The number inside the second bracket MUST be the document index (1, 2, 3, etc.)
   - The descriptive text should briefly describe the source content, NOT just say "Document X"
   - Examples:
     * Good: "Revenue increased by 15% ([Annual Report 2023][1])"
     * Good: "The CEO announced expansion plans ([Q3 Earnings Call][2])"
     * Bad: "Revenue increased by 15% ([Document 1][1])" 
     * Bad: "The CEO announced expansion plans ([Doc 2][2])" 
   - Multiple sources: "Sales grew across regions ([Q1 Report][1], [Market Analysis][3])"
   - CRITICAL: The number [1], [2], [3] etc. must match the document index from <documents>. The descriptive text helps users understand what the source is about.

6. **Structure your response clearly**:
   - Use markdown formatting (## headers, lists, **bold**, etc.) for readability
   - Break complex information into sections with ## headers when appropriate
   - Use bullet points (*) or numbered lists for multiple items
   - Highlight key numbers, dates, or facts with **bold**

# Response Guidelines

- **For greetings/casual conversation**: Respond naturally and warmly, then ask how you can help
- **For substantive questions**: Provide thorough, well-cited answers based solely on the documents
- **For follow-up questions**: Use conversation history to understand references, but still cite from documents
- **For unclear references**: If you can't determine what "it" or "that" refers to from the context, politely ask for clarification

# Special Cases

- **No relevant information found**: "I don't have information about [topic] in the provided documents. Could you provide additional context or documents?"
- **Partial information**: Answer what you can from the documents and clearly note what's missing
- **Conflicting information**: Present both perspectives with proper citations to each source
- **Ambiguous pronouns**: Use conversation history to resolve references, but cite document sources for facts

# Critical Reminders

- Prioritize accuracy over completeness - never fabricate information
- Always cite sources using the [descriptive text][number] format
- The number in citations must match the document index (1, 2, 3, etc.)
- Use descriptive text that explains what the source is, not generic labels like "Document 1"
- When uncertain, say "I don't know" or "This isn't covered in the provided documents"
- Understand conversation flow and context, but ground all facts in documents

Remember: You're having a conversation with context, but every factual claim must come from the documents with proper citations."""


NO_CONTEXT_GENERATION_PROMPT_TEMPLATE = """You are a helpful research assistant. The user has asked a question, but no relevant documents were found in the knowledge base.

# Your Response Approach

1. **For greetings/casual conversation**: 
   - Respond naturally and warmly (e.g., "Hello! How can I help you today?")
   - Be friendly and conversational

2. **For substantive questions**:
   - Politely explain that you don't have access to relevant documents to answer their question
   - Be honest and clear: "I don't have any documents available that contain information about [topic]."
   - Suggest what might help: "If you have documents about [topic], feel free to upload them and I'll be happy to help analyze them."

3. **Answer in the same language as the user's query**:
   - Vietnamese query → Vietnamese response
   - English query → English response

# What NOT to Do

- Do NOT make up information or use general knowledge to answer substantive questions
- Do NOT provide facts without document sources
- Do NOT apologize excessively - be helpful and solution-oriented

# Example Responses

**For greeting**: "Hi there! I'm here to help you find information in your documents. What would you like to know?"

**For question without docs**: "I don't have any documents available that contain information about [topic]. If you'd like, you can provide relevant documents and I'll analyze them to answer your question."

Remember: Be honest, helpful, and conversational. It's better to admit you don't have the information than to make something up."""


@singleton
class ResponseAgent:
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
    ) -> ChatPromptTemplate:
        """Prepare messages for both streaming and non-streaming responses."""
        current_query = history[-1].content

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

        messages_prompt = ChatPromptTemplate.from_messages(messages)
        return messages_prompt

    async def generate_response(
        self,
        contexts: List[Document],
        history: List[BaseMessage],
    ) -> AIMessage:
        """Generates a full response (non-streaming) based on verification results and history."""
        try:
            messages_prompt = self._prepare_messages(contexts, history)
            response_chain = messages_prompt | self.llm
            response = await response_chain.ainvoke({})
            return response

        except Exception as e:
            logger.exception(f"Error during response generation: {e}")
            raise e

    async def generate_streaming_response(
        self,
        contexts: List[Document],
        history: List[BaseMessage],
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        """Streams response content chunks and final complete message from the LLM."""
        try:
            messages_prompt = self._prepare_messages(contexts, history)
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
