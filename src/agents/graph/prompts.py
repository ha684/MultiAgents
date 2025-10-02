# src/agents/graph/prompts.py

import textwrap


class PromptTemplates:
    """Centralized prompt templates"""

    ROUTER_PROMPT = textwrap.dedent("""\
        {instructions}


        Classify into: chitchat, simple_search, or deep_research
    """)

    CONTEXTUALIZE_PROMPT = textwrap.dedent("""\
        {instructions}

        Conversation history:
        {conversation}

        Current query: {query}

        Rewrite the query to be standalone and context-aware.
    """)

    QUERY_PLANNER_PROMPT = textwrap.dedent("""\
        {instructions}

        Original Query: {original_query}

        Create a comprehensive research plan.
    """)

    VERIFICATION_PROMPT = textwrap.dedent("""\
        {instructions}

        Original Query: {original_query}
        Accumulated Knowledge: {accumulated_knowledge}
        Pending Queries: {pending_queries}
        Iteration: {iteration_count}/{max_searches}
    """)

    DYNAMIC_QUERY_GENERATOR_PROMPT = textwrap.dedent("""\
        {instructions}

        Original Query: {original_query}
        Current Knowledge: {accumulated_knowledge}
        Missing Aspects: {missing_aspects}
    """)

    FACT_CHECKER_PROMPT = textwrap.dedent("""\
        {instructions}

        Original Query: {original_query}
        Accumulated Knowledge: {accumulated_knowledge}
    """)

    FINAL_SYNTHESIZER_PROMPT = textwrap.dedent("""\
        {instructions}

        Conversation: {conversation}
        Verified Knowledge: {accumulated_knowledge}
    """)
