# src/agents/executors/__init__.py
from src.agents.executors.simple_search import RagSearchExecutor, WebSearchExecutor
from src.domain.entities.graph import SubgraphExecutor

EXECUTORS: dict[str, SubgraphExecutor] = {
    "rag_search": RagSearchExecutor(),
    "web_search": WebSearchExecutor(),
}
