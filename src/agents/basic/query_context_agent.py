# src/agents/basic/query_context_agent.py

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.agents.tools.server.mcp_retrieve_tools import think
from src.utils.decorators import singleton
from src.utils.logger_conf import logger

EXTRACT_CONTEXTUALIZED_QUERY_PROMPT = """
<instructions>
You are a query reformulation specialist. Your ONLY job is to transform the user's latest query into a comprehensive, standalone search query by incorporating relevant context from the conversation history.

You are NOT an answering agent. You do NOT provide answers, explanations, or solutions. You ONLY reformulate queries for document retrieval.
</instructions>

<core_task>
Transform the user's latest query into a self-contained search query that includes:
1. All relevant context from the conversation history
2. Specific entities, topics, and concepts mentioned earlier
3. The original intent of the user's question

The output should be a single, comprehensive query that can retrieve relevant documents without any conversation context.
</core_task>

<reformulation_process>
1. **Identify the user's latest query** - This is what needs to be reformulated
2. **Extract relevant context** from conversation history:
   - Key topics and concepts discussed
   - Specific entities (companies, technologies, people, etc.)
   - Technical terms and domain-specific vocabulary
   - Time periods or constraints mentioned
3. **Resolve references** in the latest query:
   - Replace pronouns (it, they, this, that) with specific entities
   - Replace vague references ("what else", "other ways") with specific context
   - Disambiguate between similar entities if multiple were discussed
4. **Combine** the resolved query with relevant context into one comprehensive search query
5. **Verify** the reformulated query is self-contained and preserves original intent

</reformulation_process>
"""


@singleton
class QueryContextAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        logger.info("Query Context Agent initialized successfully.")

    async def ainvoke(self, history: list[BaseMessage]) -> AIMessage:
        """
        Contextualizes the current query by using the user conversation history.
        Optionally uses the think tool for complex reformulations.
        """
        if not history:
            logger.warning("Empty history provided. Cannot contextualize query.")
            return AIMessage(content="")

        system_prompt = SystemMessage(content=EXTRACT_CONTEXTUALIZED_QUERY_PROMPT)
        user_content = HumanMessage(
            content=f"Reformulate the following query: {history[-1].content}"
        )
        messages: list[BaseMessage] = [system_prompt] + history[:-1] + [user_content]

        try:
            response = await self.iterative_llm_call_text(
                messages=messages,
                llm_with_tools=self.thinking_llm,
                available_tools={"think": think},
                max_iterations=5,
                retry_prompt="Please provide the reformulated query now.",
                fallback_value=history[-1].content,
            )
            return response

        except Exception as e:
            logger.exception(
                f"Error contextualizing query: {str(e)}. Returning original query."
            )
            return AIMessage(content=history[-1].content if history else "")
