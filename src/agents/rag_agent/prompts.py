from langchain_core.prompts import ChatPromptTemplate

summary_prompt = ChatPromptTemplate.from_template("""
    You are an expert conversation summarizer. Your task is to create a structured summary that preserves critical context for ongoing RAG conversations.

    CONVERSATION TO SUMMARIZE:
    {conversation}

    REQUIREMENTS:
    Create a JSON-structured summary with these exact fields:
    - summary: A comprehensive narrative summary
    - key_topics: List of main topics discussed
    - important_context: Critical context that impacts future responses
    - user_preferences: Any specific requirements, constraints, or preferences mentioned

    FOCUS ON:
    - Domain-specific terminology and concepts mentioned
    - User's expertise level and communication style
    - Specific document types, folders, or sources referenced
    - Unresolved questions or ongoing research threads
    - Technical requirements or constraints
    - User's stated goals or objectives

    BE CONCISE BUT COMPREHENSIVE:
    - Capture essence without unnecessary detail
    - Prioritize information that affects future query understanding
    - Include context that would be lost without the full conversation

    The summary will be used to maintain conversation continuity in a knowledge retrieval system.
    """
)
    
verification_prompt = ChatPromptTemplate.from_template("""
You are a verification agent. Analyze if search results answer the user query.

USER QUERY: {query}

SEARCH RESULTS:
{cited_documents_xml}

Evaluate:
1. COVERAGE: Does content directly address the main query intent?
2. COMPLETENESS: Are there missing information gaps?
3. RELEVANCE: How well do results match the query?

RESPOND WITH ONLY THIS JSON FORMAT:
{{
    "is_sufficient": true/false,
    "missing_aspects": ["specific gap 1", "specific gap 2"],
    "reasoning": "brief explanation why sufficient or not",
    "suggested_searches": ["alternative query 1", "alternative query 2"]
}}

Rules:
- If results comprehensively answer the query → is_sufficient: true
- If critical gaps exist → is_sufficient: false
- Be specific about missing_aspects, not generic
- Suggest 2-3 targeted searches for gaps
- Use only true/false for boolean values
- Keep reasoning under 50 words
""")

decision_prompt = ChatPromptTemplate.from_template("""
You are a decision agent. Decide whether to search more or respond based on current state.

STATE:
- Query: {original_query}
- Iterations: {search_iterations}/{max_iterations}
- Verification: {verification_summary}
- Search History: {search_history}

DECISION RULES:
RESPOND if: verification sufficient OR max iterations reached OR repeated similar searches
SEARCH if: verification shows gaps AND iterations < max AND clear improvement path exists

SEARCH TYPES (use exact lowercase):
- "focused": narrow down on specific gaps
- "broader": expand search scope  
- "alternative": try different search terms

RESPOND WITH ONLY THIS JSON FORMAT:
{{
    "next_action": "search" or "respond",
    "reasoning": "brief decision justification",
    "search_query": "optimized query string or null",
    "search_type": "focused" or "broader" or "alternative" or null
}}

Rules:
- Use exact lowercase for next_action: "search" or "respond"
- Use exact lowercase for search_type: "focused", "broader", "alternative", or null
- If next_action is "respond", set search_query and search_type to null
- Keep reasoning under 30 words
- Make search_query specific and different from previous attempts
""")
