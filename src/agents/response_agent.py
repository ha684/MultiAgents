from typing import List, Dict, AsyncGenerator, Union, Any
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import BaseMessage
from src.config.llm_config import SupportedLLMProviders
from src.llm.factory import get_llm
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from src.utils.logger_conf import logger
from src.utils.decorators import singleton

HAVE_CONTEXT_GENERATION_PROMPT_TEMPLATE = """You are an expert research assistant with access to a collection of documents. Your task is to provide accurate, well-cited answers based solely on the information contained in the provided documents.

# Core Instructions

1. **Answer in the same language as the user's query**: If the user asks in Vietnamese, respond in Vietnamese. If they ask in English, respond in English.

2. **Ground all responses in the provided documents**: 
   - Only use information explicitly stated in the documents
   - Do NOT use your general knowledge or make assumptions
   - If the documents don't contain enough information to answer fully, clearly state: "Based on the provided documents, I don't have enough information to answer [specific aspect]."

3. **Use inline citations consistently**:
   - Format: `([Descriptive name][index])` immediately after each factual claim
   - The index must match the document index from the <documents> section
   - Example: "Revenue increased by 15% ([Annual Report 2023][1])"
   - Multiple sources: "Sales grew across regions ([Q1 Report][1], [Market Analysis][3])"

4. **Structure your response clearly**:
   - Use markdown formatting (headers ##, lists, bold, etc.) for readability
   - Break complex information into sections with ## headers
   - Use bullet points (*) or numbered lists for multiple items
   - Highlight key numbers, dates, or facts with **bold**

5. **Quality standards**:
   - Be concise but complete - avoid unnecessary verbosity
   - Maintain accuracy - never misrepresent document contents
   - If multiple documents conflict, acknowledge both viewpoints and cite each
   - Use direct quotes for critical facts, placing them in quotation marks with citations

# Special Cases

- **No relevant information found**: Politely explain what information is missing
- **Partial information**: Answer what you can from the documents and clearly note what's missing  
- **Conflicting information**: Present both perspectives with proper citations

# Important Reminders

- Focus on providing well-structured content with accurate inline citations
- Always cite your sources using the [index] format from the provided documents
- When in doubt about information, acknowledge uncertainty rather than speculate

Remember: Accuracy and proper inline citation are paramount. The reference list will be generated automatically from your citations."""

NO_CONTEXT_GENERATION_PROMPT_TEMPLATE = """You are a helpful AI assistant. The user has submitted a query, but no relevant documents were found in the knowledge base to answer their question.

# Core Instructions

1. **Answer in the same language as the user's query**: Match the user's language (Vietnamese, English, etc.)

2. **Be transparent about the limitation**:
   - Politely acknowledge that no relevant documents were found
   - Explain that you can provide general information but cannot cite specific sources
   - Suggest what type of documents might be helpful if they were available

3. **Provide helpful general guidance**:
   - Offer what general knowledge you have on the topic
   - Be clear that this is general information, not sourced from their documents
   - Keep responses concise and relevant

4. **Suggest next steps**:
   - Recommend uploading relevant documents if applicable
   - Suggest refining the search query
   - Offer to help with related questions

# Response Format

Your response should follow this structure:

```
I couldn't find any relevant documents in the knowledge base to answer your question about [topic].

However, I can provide some general information:

[Your general knowledge response here]

To get more specific information, you might consider:
* [Suggestion 1]
* [Suggestion 2]
```

Remember: Be honest about the absence of documents while still being helpful with general knowledge when appropriate."""


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
