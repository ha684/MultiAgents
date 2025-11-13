# src/agents/executors/__init__.py
from typing import Dict

from src.agents.executors.simple_search import RagSearchExecutor, WebSearchExecutor
from src.domain.entities.graph import SubgraphExecutor

EXECUTORS: Dict[str, SubgraphExecutor] = {
    "rag_search": RagSearchExecutor(),
    "web_search": WebSearchExecutor(),
}
