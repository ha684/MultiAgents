# src/agents/basic/__init__.py
from src.agents.basic.citation_agent import CitationAgent
from src.agents.basic.filename_agent import FilenameAgent
from src.agents.basic.folder_categorization_agent import FolderCategorizationAgent
from src.agents.basic.query_context_agent import QueryContextAgent
from src.agents.basic.response_agent import ResponseAgent
from src.agents.basic.verification_agent import VerificationAgent
from src.agents.basic.qac_agent import QACAgent
from src.agents.basic.summary_agent import SummaryAgent
from src.agents.basic.chunk_contextual_agent import ChunkContextualAgent
from src.agents.basic.compress_agent import CompressAgent

citation_agent = CitationAgent()
summary_agent = SummaryAgent()
response_agent = ResponseAgent()
query_context_agent = QueryContextAgent()
folder_categorization_agent = FolderCategorizationAgent()
verification_agent = VerificationAgent()
qac_agent = QACAgent()
filename_agent_instance = FilenameAgent()
chunk_contextual_agent = ChunkContextualAgent()
compress_agent = CompressAgent()
