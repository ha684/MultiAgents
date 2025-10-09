from src.agents.main import OrchestratorGraph
from src.agents.graph.state import OrchestratorState
from src.models.chat import SearchProvider, WebSearchConfig
from langchain_core.messages import HumanMessage
from src.config.settings import settings
from src.utils.logger_conf import logger
import asyncio
import time

context_metadata = {"kb_id": "068dbcfd-ff20-7647-8000-c7cfdf551423"}
web_search_config = WebSearchConfig(
    provider=SearchProvider.TAVILY,
    active=False,
    api_key=settings.tavily_api_key,
)
context_metadata.update({"web_search_config": web_search_config.model_dump()})
logger.info("Initializing OrchestratorGraph...")
orchestrator_graph = OrchestratorGraph()
human_message = HumanMessage(
    content="What are the best practices and key considerations for implementing a cloud-native microservices architecture, including service discovery, load balancing, and ensuring system resilience? Use deep search",
    additional_kwargs={"message_metadata": context_metadata},
)
conversation = [human_message]
logger.info("OrchestratorGraph initialized successfully.")

logger.info("Running OrchestratorGraph...")
start_time = time.time()
final_state: OrchestratorState = asyncio.run(orchestrator_graph.run(conversation))
logger.info("OrchestratorGraph run complete.")

end_time = time.time()
logger.info(f"OrchestratorGraph run time: {end_time - start_time} seconds")
