# src/agents/executors/__init__.py
from typing import Dict

from src.agents.executors.deep_research import DeepResearchExecutor
from src.agents.executors.simple_search import RagSearchExecutor, WebSearchExecutor
from src.agents.executors.sql_query import SqlQueryExecutor
from src.domain.entities.graph import SubgraphExecutor

EXECUTORS: Dict[str, SubgraphExecutor] = {
    "rag_search": RagSearchExecutor(),
    "web_search": WebSearchExecutor(),
    "deep_research": DeepResearchExecutor(),
    "sql_query": SqlQueryExecutor(),
}
