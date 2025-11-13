# src/agents/basic/__init__.py
from __future__ import annotations

from src.agents.basic.citation_agent import CitationAgent
from src.agents.basic.compress_agent import CompressAgent
from src.agents.basic.qac_agent import QACAgent
from src.agents.basic.response_agent import ResponseAgent
from src.agents.basic.summary_agent import SummaryAgent
from src.agents.basic.verification_agent import VerificationAgent
from src.agents.basic.reflection_agent import ReflectionAgent

citation_agent = CitationAgent()
summary_agent = SummaryAgent()
response_agent = ResponseAgent()
verification_agent = VerificationAgent()
qac_agent = QACAgent()
compress_agent = CompressAgent()
reflection_agent = ReflectionAgent()
