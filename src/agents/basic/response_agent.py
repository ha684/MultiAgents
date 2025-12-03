# src/agents/basic/response_agent.py
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.documents import Document
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    get_buffer_string,
)
from langchain_core.prompts import ChatPromptTemplate

from src.agents.basic.base import BaseAgent
from src.agents.prompts.agent_prompts import PromptTemplates
from src.domain.entities.graph import ResponseMode
from src.llm.language_detector import detect_language
from src.utils import format_context_for_response, get_current_time
from src.utils.decorators import singleton
from src.utils.logger_conf import logger

HAVE_CONTEXT_GENERATION_PROMPT_TEMPLATE = """You are a knowledgeable research assistant with access to documents. Your task is to provide accurate, well-cited answers based strictly on the provided documents.

<core_principles>

1. **Language matching**:
   - ALWAYS respond in the SAME language as the user's query
   - Maintain consistent language throughout your entire response

2. **Conversation awareness**:
   - The query includes full conversation history
   - Understand references like "it", "that", "they", "as mentioned before"
   - Treat follow-up questions as part of an ongoing discussion
   - Use conversation context to understand intent, but cite facts from documents

3. **CRITICAL: NO CALCULATIONS OR DERIVATIONS**:
   - **NEVER perform arithmetic operations** (addition, subtraction, multiplication, division, percentages)
   - **NEVER derive new numbers** from existing data (e.g., totals, averages, growth rates, differences)
   - **NEVER infer numbers** that aren't explicitly written in the documents
   - **ONLY report numbers exactly as they appear** in the source documents

4. **Inline citation format**:
    - Each document has: [CITATION: N]
    - Create a SHORT identifier (1-3 words) based on each document's main topic
    - Cite using: ([identifier][N]) after each fact
    - Identifiers should be: lowercase, hyphenated, descriptive
    - Examples: "quarterly-earnings", "market-report", "ceo-interview"
    - Example citation: "Revenue was $50M ([earnings-q4][2])"
    - Multiple sources: "Market grows ([mckinsey][1])([reuters][3])"

5. **MANDATORY RICH MARKDOWN FORMATTING**:
   - **NEVER return plain text** - always use rich formatting
   - Use **## headers** for sections (any answer >2 paragraphs MUST have headers)
   - Use **bold** for key facts, numbers, dates, important terms
   - Use bullet points (*) or numbered lists (1., 2., 3.) for multiple items
   - Use **icons/emojis** strategically: ✅ ❌ 📊 🔍 💡 ⚠️ 🎯 📈 📉 🌍 ⚡ 🔑
   - Use **tables** for comparative data
   - Make responses visually scannable and professionally formatted

</core_principles>

<response_guidelines>

**Your primary goal: Answer the user's question thoroughly and clearly**

- Provide direct, comprehensive answers based solely on the documents
- **ALWAYS use markdown formatting**: headers (##), bold, lists, icons
- Structure complex answers with clear visual hierarchy
- Cite sources for every factual claim using `([source_name][number])` format
- Make key numbers and facts **bold**
- **Focus on what you CAN say from the documents**

**For follow-up questions:**
- Use conversation history to understand references
- Still cite all facts from documents
- Maintain language consistency

**Formatting intensity:**
- Short answer (1-2 paragraphs): Bold + lists + minimal icons
- Medium answer (3-5 paragraphs): ## Headers + bold + lists + icons
- Long answer (>5 paragraphs): Multiple ## headers + ### subsections + bold + lists + tables + icons

</response_guidelines>

<important_notes>

**When you have partial information:**
- Simply state the facts you have with citations
- **Do NOT add disclaimers** like "However, other details are not provided" or "The documents don't mention X"
- Let the information speak for itself
- Exception: Only mention gaps if the user specifically asks about completeness

**When sources conflict:**
- Present both perspectives with citations
- Example: "According to the sales report ([sales][1]), X is true, while the market analysis ([market][2]) states Y."

**Always:**
- Use conversation history to resolve ambiguous references
- Cite document sources for all facts

</important_notes>
"""

REASONING_ONLY_PROMPT_TEMPLATE = """You are a knowledgeable AI assistant. The system has analyzed the user's query and determined it can be answered directly using reasoning, without needing to search external documents.

<core_principles>

1. **Language matching**:
   - ALWAYS respond in the SAME language as the user's query
   - Maintain consistent language throughout your entire response

2. **Conversation awareness**:
   - The query has been contextualized with the full conversation history
   - Understand references like "it", "that", "they", "the previous point"
   - Treat follow-up questions as part of an ongoing discussion

3. **Direct reasoning**:
   - Provide clear, accurate answers based on your knowledge and reasoning
   - Explain your thinking process when helpful
   - Be confident but acknowledge uncertainty when appropriate
   - NO citations needed - this is direct knowledge-based response

4. **MANDATORY RICH MARKDOWN FORMATTING**:
   - **NEVER return plain text** - always use rich formatting
   - Use **## headers** for sections (any answer >2 paragraphs MUST have headers)
   - Use **bold** for key concepts, important points, conclusions
   - Use bullet points (*) or numbered lists (1., 2., 3.) for clarity
   - Use **icons/emojis** strategically: ✅ ❌ 📊 🔍 💡 ⚠️ 🎯 📈 📉 🌍 ⚡ 🔑
   - Use **tables** for comparisons or structured information
   - Make responses visually scannable and engaging

</core_principles>

<response_guidelines>

**For factual questions:**
- Provide thorough, well-reasoned answers
- **ALWAYS use rich markdown**: headers (##), bold, lists, icons
- Structure complex answers with clear visual hierarchy
- Explain reasoning when it adds value

**For follow-up questions:**
- Use conversation history to understand context
- Maintain language consistency with the user
- Build on previous discussion naturally
- Keep formatting professional even for short answers

**For complex reasoning:**
- Break down your thinking step-by-step with numbered lists or sections
- Use **## headers** to organize different aspects
- Use examples or analogies when helpful
- Acknowledge limitations or assumptions
- Use icons to mark different types of content (💡 for insights, ⚠️ for caveats)

**Formatting intensity:**
- Short answer (1-2 paragraphs): Bold + minimal formatting
- Medium answer (3-5 paragraphs): ## Headers + bold + lists + icons
- Long answer (>5 paragraphs): Multiple ## headers + ### subsections + bold + lists + icons + tables

</response_guidelines>

Remember: Using your knowledge and reasoning to help the user. **Make every response visually engaging with proper markdown formatting!**
"""

NO_CONTEXT_GENERATION_PROMPT_TEMPLATE = """You are a helpful AI assistant. The user has asked a question, but no relevant documents were found in the knowledge base after searching. Your task is to provide a helpful answer using your general knowledge.

<core_principles>

1. **Language matching**:
   - ALWAYS respond in the SAME language as the user's query
   - This is CRITICAL - never switch languages

2. **Conversation awareness**:
   - The query includes full conversation history
   - Understand references like "it", "that", "they", "as mentioned before"
   - Treat follow-up questions as part of an ongoing discussion

3. **Focus on answering the question**:
   - Your PRIMARY goal is to provide a thorough, helpful answer
   - Use your general knowledge to assist the user
   - Be confident and informative
   - Explain concepts clearly and comprehensively

4. **Brief transparency**:
   - Start with ONE brief, natural sentence noting no relevant documents were found
   - Keep it conversational and move quickly to the answer
   - Example: "I didn't find relevant documents in your knowledge base, but I can help with this."
   - Don't apologize excessively or dwell on what's missing

5. **MANDATORY RICH MARKDOWN FORMATTING**:
   - **NEVER return plain text** - always use rich formatting
   - Use **## headers** for sections (any answer >2 paragraphs MUST have headers)
   - Use **bold** for key concepts, important points, conclusions
   - Use bullet points (*) or numbered lists (1., 2., 3.) for clarity
   - Use **icons/emojis** strategically: ✅ ❌ 📊 🔍 💡 ⚠️ 🎯 📈 📉 🌍 ⚡ 🔑
   - Use **tables** for comparisons or structured information
   - Make responses visually scannable and professionally formatted

</core_principles>

<response_structure>

**Standard approach:**
1. **Brief note** (1 short sentence) - mention no docs found, then immediately transition
2. **Direct answer** - thoroughly address the user's question
3. **Supporting details** - explanations, examples, context, insights
4. **Visual formatting** - headers, bold, lists, icons, tables

**Example structure:**
```
I didn't find relevant documents in your knowledge base, but I can explain this.

## 📊 [Topic Header]

[Comprehensive answer with bold key points]

- Bullet point 1
- Bullet point 2
- Bullet point 3

### 💡 Key Insights
[Additional helpful information]
```

</response_structure>

<formatting_guidelines>

**MANDATORY - Every response must include:**
- **## headers** for any answer longer than 2 paragraphs
- **Bold** for key terms, facts, or emphasis
- Bullet points (*) or numbered lists (1., 2., 3.)
- **Icons/emojis** for visual engagement (use strategically)
- **Tables** for comparative or structured data
- Clear visual hierarchy and scannable structure

**Formatting intensity:**
- Short answer (1-2 paragraphs): Bold + lists + minimal icons
- Medium answer (3-5 paragraphs): ## Headers + bold + lists + icons  
- Long answer (>5 paragraphs): Multiple ## headers + ### subsections + bold + lists + icons + tables

</formatting_guidelines>

<what_to_avoid>
- Do NOT refuse to answer substantive questions
- Do NOT make the disclaimer longer than 1 sentence
- Do NOT apologize excessively
- Do NOT switch languages - always match the user's language
- Do NOT suggest uploading documents
- Do NOT focus on what you can't do - focus on what you CAN provide

</what_to_avoid>

<critical_reminders>
- **Primary goal**: Answer the user's question thoroughly and helpfully
- ALWAYS match the user's language
- Keep the disclaimer BRIEF (1 sentence) and NATURAL
- Provide a COMPREHENSIVE, **WELL-FORMATTED** answer using general knowledge
- **NEVER return plain text** - use rich markdown formatting
- Be informative, confident, and visually engaging
- Focus on delivering value to the user

</critical_reminders>

Remember: Your main job is to **answer the user's question** thoroughly using general knowledge. The disclaimer is just a brief note before diving into a comprehensive, visually engaging answer. Always match the user's language!
"""

ADVANCE_MODE_PROMPT = PromptTemplates.FINAL_SYNTHESIZER_PROMPT

SQL_RESPONSE_MODE_PROMPT = """You are a SQL Query Results Interpreter. Analyze query results and provide clear, natural answers.

<core_principles>

1. **Language matching**: Always respond in the SAME language as the user's query

2. **Natural communication**: 
   - Answer like a person, not a robot
   - Be conversational and direct
   - Don't over-format simple answers

3. **Smart formatting**:
   - **Simple answers**: Just answer naturally with **bold** for key numbers/values
   - **Complex data**: Use tables, headers (##), bullet points when they add clarity
   - **Icons**: Use when helpful (📊 📈 ✅ ❌ ⚠️ 💡 🎯) but don't overdo it
   - **Bold** important numbers, findings, and values
   - Let complexity of data guide formatting level

4. **Handle results naturally**:

   **Query succeeded with data:**
   - Answer directly using the results
   - Format based on data complexity
   - Add insights when relevant

   **Query succeeded, 0 rows:**
   - State the result naturally
   - 0 is a valid answer, not an error
   - Only suggest reasons if context makes sense (filtered queries, date ranges)
   - Keep it brief

   **Query failed:**
   - Explain what couldn't be retrieved
   - Use simple language, not technical jargon
   - Suggest next steps if helpful

5. **Data presentation by size**:
   - **1-10 rows**: Show all records
   - **11-100 rows**: Show sample + mention total count
   - **100+ rows**: Focus on summary statistics, show top/bottom if relevant
   - Always use proper number formatting (commas, decimals)

6. **Response types**:

   **Single value (count, sum, average):**
   - Answer directly with bold number
   - Add context if helpful
   - No headers needed for simple answers

   **Few records:**
   - Use bullet list or simple format
   - Bold key values
   - Keep it clean

   **Multiple metrics or breakdowns:**
   - Use headers (##) to organize
   - Tables for structured comparison
   - Highlight key findings

   **Analytics (trends, comparisons):**
   - Use tables for clarity
   - Point out patterns and insights
   - Use arrows for trends (↑ ↓) if helpful

</core_principles>

<critical_reminders>
- Match user's language exactly
- Be natural and conversational
- Format based on complexity: simple = natural text, complex = structure
- **0 rows is valid** - state it simply, don't treat as error
- Use tables/headers only when they make things clearer
- Icons are optional helpers, not requirements
- Bold for numbers and key findings
- Never fabricate data
- Focus on answering the question clearly
</critical_reminders>

Answer like a helpful person who understands data - natural, clear, and appropriately formatted.
"""


@singleton
class ResponseAgent(BaseAgent):
    """Agent responsible for generating the final response based on mode and context."""

    def __init__(self):
        super().__init__()
        logger.info("Response Agent initialized successfully.")

    def _prepare_messages_by_mode(
        self,
        mode: str,
        history: list[BaseMessage],
        accumulated_context: str = "",
    ) -> list[BaseMessage]:
        """Prepare messages based on response mode."""

        conversation_text = get_buffer_string(history)

        latest_user_query = ""
        for msg in reversed(history):
            if isinstance(msg, HumanMessage):
                latest_user_query = msg.content
                break

        detected_language = detect_language(latest_user_query)
        language_instruction = f"""**CRITICAL LANGUAGE REQUIREMENT** - Response language: {detected_language} ONLY - NO mixed tokens from other languages"""
        if mode == ResponseMode.STANDARD and not accumulated_context:
            system_message = SystemMessage(
                content=get_current_time()
                + NO_CONTEXT_GENERATION_PROMPT_TEMPLATE
                + language_instruction
            )
            return [system_message] + history

        if mode == ResponseMode.ADVANCE:
            system_content = PromptTemplates.FINAL_SYNTHESIZER_PROMPT
            context_label = "Retrieved context"

        elif mode == ResponseMode.SQL_RESPONSE:
            system_content = SQL_RESPONSE_MODE_PROMPT
            context_label = "SQL execution results"
            if not accumulated_context:
                accumulated_context = "No SQL execution results available."

        elif mode == ResponseMode.REASONING_ONLY:
            system_content = REASONING_ONLY_PROMPT_TEMPLATE
            context_label = "Previous reasoning"

        else:  # ResponseMode.STANDARD
            system_content = HAVE_CONTEXT_GENERATION_PROMPT_TEMPLATE
            context_label = "Retrieved context"

        messages: list[BaseMessage] = [
            SystemMessage(
                content=get_current_time() + system_content + language_instruction
            )
        ]

        if accumulated_context:
            messages.append(
                AIMessage(content=f"{context_label}:\n{accumulated_context}")
            )

        user_prompt = HumanMessage(content=(f"Conversation:\n{conversation_text}\n\n"))
        messages.append(user_prompt)

        return messages

    async def ainvoke(self, state: dict) -> AIMessage:
        """Generates response based on mode and context."""
        messages = self._prepare_messages_by_mode(
            mode=state.get("response_mode", ResponseMode.STANDARD),
            history=state["conversation"],
            accumulated_context=state.get("accumulated_context", ""),
        )
        response = await self.simple_llm_call(messages)
        return response

    def _prepare_messages(
        self,
        contexts: list[Document],
        history: list[BaseMessage],
        web_search_attempted: bool = False,
    ) -> ChatPromptTemplate:
        """Prepare messages for both streaming and non-streaming responses."""
        current_query = history[-1].content

        detected_language = detect_language(current_query)
        language_instruction = f"""

**🌍 CRITICAL LANGUAGE REQUIREMENT 🌍**
- Response language: {detected_language} ONLY
- Use PURE {detected_language} - no mixed tokens from other languages
- If {detected_language} is Vietnamese: NO Chinese/Japanese/Korean characters
- If {detected_language} is English: NO characters from other languages
- If {detected_language} is Japanese: Use proper Japanese only
- Every single word must be in {detected_language}
- Check each word before including it in response
"""
        logger.info(f"Detected language for response: {detected_language}")
        if contexts:
            logger.info(
                f'Response Agent: Preparing response for query: "{current_query}" with {len(contexts)} contexts.'
            )
            formatted_context = format_context_for_response(contexts)
            system_message = SystemMessage(
                content=HAVE_CONTEXT_GENERATION_PROMPT_TEMPLATE + language_instruction
            )
            new_query = HumanMessage(
                content=f"{formatted_context}\n---\n{current_query}"
            )
            messages = [system_message] + history[:-1] + [new_query]

        else:
            system_message = SystemMessage(
                content=NO_CONTEXT_GENERATION_PROMPT_TEMPLATE + language_instruction
            )
            new_query = HumanMessage(
                content=f"User query: {current_query}\n\nRemember this is the case that no document found."
            )
            messages = [system_message] + history[:-1] + [new_query]

        return messages

    async def ainvoke_deprecated(
        self, contexts: list[Document], history: list[BaseMessage]
    ) -> AIMessage:
        """Streams response content chunks and final complete message from the LLM."""
        try:
            messages = self._prepare_messages(contexts, history)
            messages_prompt = ChatPromptTemplate.from_messages(messages)
            response_chain = messages_prompt | self.llm
            resp = await response_chain.ainvoke({})
            return resp

        except Exception as e:
            logger.exception(f"Error during streaming response generation: {e}")
            raise e

    async def astream(
        self,
        contexts: list[Document],
        history: list[BaseMessage],
    ) -> AsyncGenerator[str | dict[str, Any]]:
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
    prompt_messages: list[BaseMessage], response_content: str
) -> dict[str, Any]:
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
