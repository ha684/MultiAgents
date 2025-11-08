# src/agents/basic/__init__.py
from __future__ import annotations

from src.agents.basic.chunk_contextual_agent import ChunkContextualAgent
from src.agents.basic.citation_agent import CitationAgent
from src.agents.basic.compress_agent import CompressAgent
from src.agents.basic.filename_agent import FileNameAgent
from src.agents.basic.folder_categorization_agent import FolderCategorizationAgent
from src.agents.basic.qac_agent import QACAgent
from src.agents.basic.query_context_agent import QueryContextAgent
from src.agents.basic.response_agent import ResponseAgent
from src.agents.basic.summary_agent import SummaryAgent
from src.agents.basic.verification_agent import VerificationAgent
from src.agents.basic.router_agent import RouterAgent
from src.agents.basic.reflection_agent import ReflectionAgent
from src.agents.basic.planner_agent import PlannerAgent
from src.agents.basic.dynamic_query_agent import DynamicQueryAgent

citation_agent = CitationAgent()
summary_agent = SummaryAgent()
response_agent = ResponseAgent()
query_context_agent = QueryContextAgent()
folder_categorization_agent = FolderCategorizationAgent()
verification_agent = VerificationAgent()
qac_agent = QACAgent()
file_name_agent = FileNameAgent()
chunk_contextual_agent = ChunkContextualAgent()
compress_agent = CompressAgent()
router_agent = RouterAgent()
reflection_agent = ReflectionAgent()
planner_agent = PlannerAgent()
dynamic_query_agent = DynamicQueryAgent()
