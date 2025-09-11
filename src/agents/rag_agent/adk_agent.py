from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from contextlib import AsyncExitStack
from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from ..task_manager import AgentWithTaskManager
from ..tools.server.mcp_retrieve_tools import (
    search,
    think,
)
import os
from google.adk.sessions.database_session_service import DatabaseSessionService
from ...prompts.rag_agent_prompt import DEFAULT_DOCUMENT_SEARCH_AGENT_PROMPT
from google.genai import types
from google.adk.models.lite_llm import LiteLlm
# tools = MCPToolset(
#     connection_params=SseServerParams(
#         url=os.getenv('MCP_SERVER_URL'),
#     ),
# )
from langgraph.types import Command


class DocumentSearchAgent(AgentWithTaskManager):
    """An agent that handles document search and retrieval requests."""

    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']

    def __init__(self):
        self._agent = self._build_agent()
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=DatabaseSessionService(db_url=os.getenv('SYNC_DATABASE_URL')),
            memory_service=InMemoryMemoryService(),
        )

    def get_processing_message(self) -> str:
        return 'Searching documents...'

    def _build_agent(self) -> LlmAgent:
        """Builds the LLM agent for the document search agent."""
        return LlmAgent(
            model=os.getenv('GOOGLE_API_MODEL'),
            name='DocumentSearchAgent',
            description=(
                'A specialized agent that searches and retrieves relevant documents from databases. '
                'Efficiently finds the most relevant content based on user queries and provides organized results.'
            ),
            instruction=DEFAULT_DOCUMENT_SEARCH_AGENT_PROMPT,
            tools=[
                search,
                think,
            ],
            generate_content_config=types.GenerateContentConfig(
                temperature=float(os.getenv("GOOGLE_API_TEMPERATURE", 0.7)),
                max_output_tokens=16384
            )
        )