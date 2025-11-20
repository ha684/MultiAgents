# src/agents/basic/__init__.py
from __future__ import annotations

from src.agents.basic.action_execution_agent import ActionExecutionAgent
from src.agents.basic.citation_agent import CitationAgent
from src.agents.basic.compress_agent import CompressAgent
from src.agents.basic.direction_generation_agent import DirectionGenerationAgent
from src.agents.basic.phase_agent import PhaseAgent
from src.agents.basic.qac_agent import QACAgent
from src.agents.basic.query_context_agent import QueryContextAgent
from src.agents.basic.response_agent import ResponseAgent
from src.agents.basic.summary_agent import SummaryAgent
from src.agents.basic.verification_agent import VerificationAgent

citation_agent = CitationAgent()
summary_agent = SummaryAgent()
response_agent = ResponseAgent()
verification_agent = VerificationAgent()
qac_agent = QACAgent()
compress_agent = CompressAgent()
direction_generation_agent = DirectionGenerationAgent()  # Legacy
phase_agent = PhaseAgent()
action_execution_agent = ActionExecutionAgent()
query_context_agent = QueryContextAgent()
