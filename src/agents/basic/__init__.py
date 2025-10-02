# src/agents/basic/__init__.py
from .citation_agent import CitationAgent
from .filename_agent import FilenameAgent
from .folder_categorization_agent import FolderCategorizationAgent
from .query_context_agent import QueryContextAgent
from .response_agent import ResponseAgent
from .verification_agent import VerificationAgent
from .qac_agent import QACAgent
from .summary_agent import SummaryAgent
from .chunk_contextual_agent import ChunkContextualAgent

citation_agent = CitationAgent()
summary_agent = SummaryAgent()
response_agent = ResponseAgent()
query_context_agent = QueryContextAgent()
folder_categorization_agent = FolderCategorizationAgent()
verification_agent = VerificationAgent()
qac_agent = QACAgent()
filename_agent = FilenameAgent()
chunk_contextual_agent = ChunkContextualAgent()
