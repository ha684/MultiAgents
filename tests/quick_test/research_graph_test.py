# tests/quick_test/research_graph_test.py
"""Quick test for refactored ResearchGraph"""

import asyncio
from src.agents.graph.research_graph import ResearchGraph
from src.domain.entities.state import ResearchState
from src.domain.schemas.chat import SearchProvider, WebSearchConfig
from src.core.config.settings import settings
from src.utils.logger_conf import logger


async def test_research_graph():
    """Test the refactored research graph with a simple query"""

    # Setup context
    context_metadata = {
        "kb_id": "068dbcfd-ff20-7647-8000-c7cfdf551423",
        "web_search_config": WebSearchConfig(
            provider=SearchProvider.TAVILY,
            active=True,
            api_key=settings.tavily_api_key,
        ).model_dump(),
    }

    # Create research state
    research_state = ResearchState(
        contextualized_query="What are the main features of Python programming language?",
        context_metadata=context_metadata,
        breadth=2,  # 2 searches per depth level
        depth=2,  # 2 depth iterations
    )

    logger.info("=" * 70)
    logger.info("Testing Refactored ResearchGraph")
    logger.info("=" * 70)
    logger.info(f"Query: {research_state['contextualized_query']}")
    logger.info("Breadth: 2 searches per depth")
    logger.info("Depth: 2 iterations")
    logger.info("=" * 70)

    # Run research graph
    graph = ResearchGraph()
    result = await graph.ainvoke(research_state)

    if result.status == "success":
        state = result.state
        logger.info("\n" + "=" * 70)
        logger.info("RESEARCH COMPLETED SUCCESSFULLY")
        logger.info("=" * 70)
        logger.info(f"Total Searches: {state.get('search_count', 0)}")
        logger.info(f"Total Citations: {state.get('citation_counter', 0)}")
        logger.info(f"Depth Levels Completed: {state.get('current_depth_level', 0)}")
        logger.info(f"Learnings Count: {len(state.get('learnings', []))}")
        logger.info("=" * 70)

        # Print learnings
        logger.info("\nLEARNINGS:")
        for i, learning in enumerate(state.get("learnings", []), 1):
            logger.info(f"{i}. {learning[:150]}...")

        # Print accumulated knowledge (truncated)
        knowledge = state.get("accumulated_knowledge", "")
        logger.info("\nACCUMULATED KNOWLEDGE (first 500 chars):")
        logger.info(knowledge[:500] + "..." if len(knowledge) > 500 else knowledge)

        logger.info("\n" + "=" * 70)
        logger.info("TEST PASSED ✓")
        logger.info("=" * 70)
    else:
        logger.error("=" * 70)
        logger.error("RESEARCH FAILED")
        logger.error("=" * 70)
        logger.error(f"Error: {result.message}")
        logger.error("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_research_graph())
