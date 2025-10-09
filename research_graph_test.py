from src.agents.graph.research_graph import ResearchGraph
from src.agents.graph.state import ResearchState
from src.utils.logger_conf import logger
import asyncio
import time

context_metadata = {"kb_id": "068dbcfd-ff20-7647-8000-c7cfdf551423"}

logger.info("Initializing ResearchGraph...")
research_graph = ResearchGraph()
reserach_state = ResearchState(
    contextualized_query="What are the best practices and key considerations for implementing a cloud-native microservices architecture, including service discovery, load balancing, and ensuring system resilience?",
    context_metadata=context_metadata,
)
logger.info("ResearchGraph initialized successfully.")

logger.info("Running ResearchGraph...")
start_time = time.time()
final_state: ResearchState = asyncio.run(research_graph.run(reserach_state))
logger.info("ResearchGraph run complete.")

end_time = time.time()
logger.info(f"ResearchGraph run time: {end_time - start_time} seconds")

logger.info(f"Final accumulated knowledge: \n\n {final_state['accumulated_knowledge']}")
