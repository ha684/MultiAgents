from langchain_core import output_parsers
from langchain_core.prompts import ChatPromptTemplate
from typing import List
from src.llm.factory import get_llm
from src.utils.logger_conf import logger
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from src.utils.decorators import singleton

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
4. **Combine** the resolved query with relevant context into one comprehensive search query

</reformulation_process>

<examples>
**Example 1:**
Conversation Context: Discussion about noise in SFT data for LLMs, challenges of overfitting to noise, mitigation strategies like careful data selection and noise injection strategies.
User's Latest Query: "what else can we do?"
Reformulated Query: "What additional strategies and methods can be used to mitigate the impact of noise in SFT supervised fine-tuning data for LLMs beyond careful data selection, noise injection strategies, language-specific considerations, and larger training sets?"

**Example 2:**
Conversation Context: Discussion about Tesla's financial performance, Elon Musk's leadership decisions, stock price volatility.
User's Latest Query: "How did this affect their market share?"
Reformulated Query: "How did Tesla's financial performance and Elon Musk's leadership decisions affect Tesla's electric vehicle market share?"

**Example 3:**
Conversation Context: Analysis of Microsoft's AI initiatives, Azure cloud platform, recent partnerships.
User's Latest Query: "What about their competitors?"
Reformulated Query: "What are the AI initiatives and cloud platform strategies of Microsoft's competitors in response to Microsoft's Azure platform and AI partnerships?"

**Example 4:**
Conversation Context: Discussion about renewable energy adoption in Europe vs Asia, solar power growth trends.
User's Latest Query: "Compare the investment levels"
Reformulated Query: "Compare the investment levels in renewable energy between Europe and Asia, particularly focusing on solar power infrastructure and growth trends"
</examples>

<critical_rules>
**YOU MUST:**
- Output ONLY the reformulated query as a single sentence or phrase
- Include specific entities, topics, and technical terms from the conversation
- Make the query completely self-contained
- Preserve the user's original question intent
- Create a query optimized for document retrieval

**YOU MUST NOT:**
- Provide answers, explanations, or solutions
- Add numbered lists, bullet points, or formatting
- Include phrases like "Additional strategies include:" or "Here are some ways:"
- Generate multiple queries or options
- Add introductory or concluding statements
- Use markdown formatting or special characters

**OUTPUT FORMAT:**
Return only a single, comprehensive query string with no additional text, formatting, or explanations.
</critical_rules>

Remember: You are reformulating queries for retrieval systems, NOT answering questions. The reformulated query will be used to find relevant documents that can answer the user's question.
"""


@singleton
class QueryContextAgent:
    def __init__(self):
        self.llm = get_llm("nxchat")
        logger.info("Query Context Agent initialized successfully.")

    async def contextualize_query(self, history: List[BaseMessage]) -> str:
        """
        Contextualizes the current query by using the user conversation history.

        Args:
            query (str): The current input query from the user.
            conversation_history (List[MessageCreateRequest]): A list of MessageCreateRequest
                                                    representing the conversation history.
                                                    Each dictionary should have 'role' (e.g., "user", "assistant")
                                                    and 'content' keys.
                                                    representing the conversation history.
                                                    Each dictionary should have 'role' (e.g., "user", "assistant")
                                                    and 'content' keys.

        Returns:
            str: The contextualized query containing all important information.
            str: The contextualized query containing all important information.
        """
        system_prompt = SystemMessage(content=EXTRACT_CONTEXTUALIZED_QUERY_PROMPT)
        user_content = HumanMessage(
            content=f"Reformulate the following query: {history[-1].content}"
        )
        messages = [system_prompt] + history[:-1] + [user_content]
        prompt = ChatPromptTemplate.from_messages(messages)
        response_chain = prompt | self.llm | output_parsers.StrOutputParser()
        try:
            contextualized_query = await response_chain.ainvoke({})

            if not contextualized_query:
                logger.warning(
                    "No contextualized query returned from LLM response. Returning original query."
                )
                return history[-1].content
                return history[-1].content

            contextualized_query = contextualized_query.strip()

            return contextualized_query
        except Exception as e:
            logger.exception(
                f"Error contextualizing query: {str(e)}. Returning original query."
            )
            return history[-1].content
            return history[-1].content


# Example Usage:
if __name__ == "__main__":
    context_agent = QueryContextAgent()

    # --- Test Case 1: Query needs contextualization ---
    history_1 = [
        {"role": "user", "content": "What is the capital of France?"},
        {"role": "assistant", "content": "The capital of France is Paris."},
    ]
    query_1 = "And what about Germany?"
    print(f"Original Query 1: '{query_1}'")
    print("History 1:")
    for h in history_1:
        print(f"  {h['role']}: {h['content']}")
    contextualized_1 = context_agent.contextualize_query(query_1, history_1)
    print(f"Contextualized Query 1: '{contextualized_1}'\n")

    # --- Test Case 2: Query is self-contained ---
    history_2 = [
        {"role": "user", "content": "Tell me a joke."},
        {
            "role": "assistant",
            "content": "Why don't scientists trust atoms? Because they make up everything!",
        },
    ]
    query_2 = "What is the tallest mountain in the world?"
    print(f"Original Query 2: '{query_2}'")
    print("History 2:")
    for h in history_2:
        print(f"  {h['role']}: {h['content']}")
    contextualized_2 = context_agent.contextualize_query(query_2, history_2)
    print(f"Contextualized Query 2: '{contextualized_2}'\n")

    # --- Test Case 3: Empty history ---
    history_3 = []
    query_3 = "How much does a polar bear weigh?"
    print(f"Original Query 3: '{query_3}'")
    print("History 3: (Empty)")
    contextualized_3 = context_agent.contextualize_query(query_3, history_3)
    print(f"Contextualized Query 3: '{contextualized_3}'\n")
