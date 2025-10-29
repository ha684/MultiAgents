# src/agents/graph/__init__.py
from src.agents.graph.research_graph import ResearchGraph
from src.agents.graph.simple_search_graph import SimpleSearchGraph
from src.agents.graph.sql_graph import SqlGraph

sql_graph = SqlGraph()
research_graph = ResearchGraph()
simple_search_graph = SimpleSearchGraph()
