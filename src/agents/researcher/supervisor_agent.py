import uuid
import asyncio
from typing import Any, cast
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
    BaseMessage,
)
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from typing_extensions import TypedDict
from src.agents.researcher import prompts
from src.llm.factory import get_llm
from src.agents.researcher.research_agent import ResearchAgent
from src.agents.researcher.tools import ConductResearch
from pydantic import BaseModel
from src.utils.logger_conf import logger


class SupervisorState(TypedDict):
    """
    SupervisorState is a state that contains messages and research results.
    """

    supervisor_messages: list[BaseMessage]
    token_usage: int
    file_references: list[str]
    chunk_references: list[str]
    compressed_research: str
    notes: str


class SupervisorInputState(BaseModel):
    """
    Define input schema for supervisor agent
    """

    research_brief: str
    supervisor_messages: list[BaseMessage]
    token_usage: int


class SupervisorOutputState(BaseModel):
    """
    Define output schema for supervisor agent
    """

    supervisor_messages: list[BaseMessage]
    compressed_research: str
    chunk_references: list[str]
    file_references: list[str]
    notes: str
    token_usage: int


class SupervisorAgent:
    def __init__(self, kb_id: uuid.UUID, config: dict[str, Any]):
        self.config = config
        self.kb_id = kb_id
        logger.info(f"Initializing SupervisorAgent with kb_id: {kb_id}")
        self.graph = StateGraph(
            state_schema=SupervisorState,
            input=SupervisorInputState,
            output=SupervisorOutputState,
        )
        self.researcher = ResearchAgent(kb_id, config).compile()

        self.graph.add_node("supervisor", self.supervisor)
        self.graph.add_node("execute_research", self.execute_research)

        self.graph.add_edge(START, "supervisor")
        self.graph.add_edge("supervisor", "execute_research")
        self.graph.add_edge("execute_research", END)

        self.tools = [ConductResearch]
        self.llm = get_llm("nxchat")

    def compile(self):
        return self.graph.compile()

    async def execute_research(self, state: SupervisorState):
        """Execute all research tasks concurrently"""
        logger.debug("SupervisorAgent.execute_research called")
        supervisor_messages = state.get("supervisor_messages", [])
        token_usage = state.get("token_usage", 0)

        if not supervisor_messages:
            logger.info("No supervisor messages, ending research")
            return Command(
                goto=END,
                update={
                    "notes": "",
                    "chunk_references": [],
                    "file_references": [],
                    "compressed_research": "",
                    "token_usage": token_usage,
                },
            )

        most_recent_message = cast(AIMessage, supervisor_messages[-1])

        try:
            conduct_research_calls = [
                tool_call
                for tool_call in most_recent_message.tool_calls or []
                if tool_call["name"] == "ConductResearch"
            ]

            if not conduct_research_calls:
                logger.info("No research tasks to execute")
                return Command(
                    goto=END,
                    update={
                        "notes": "",
                        "chunk_references": state.get("chunk_references", []),
                        "file_references": state.get("file_references", []),
                        "compressed_research": state.get(
                            "compressed_research", "No research tasks were created"
                        ),
                        "token_usage": token_usage,
                    },
                )

            research_tasks = []
            for tool_call in conduct_research_calls:
                if not tool_call["args"].get("research_topic"):
                    logger.warning(
                        f"Skipping ConductResearch tool call {tool_call['id']} - no research topic"
                    )
                    continue

                research_topic = tool_call["args"]["research_topic"]
                logger.info(f"Creating research task for: {research_topic}")

                task = self.researcher.ainvoke(
                    {
                        "researcher_messages": [
                            SystemMessage(content=prompts.research_system_prompt),
                            HumanMessage(content=research_topic),
                        ],
                        "research_topic": research_topic,
                        "token_usage": 0,
                    }
                )
                research_tasks.append(task)

            logger.info(f"Executing {len(research_tasks)} research tasks concurrently")
            research_results = await asyncio.gather(
                *research_tasks, return_exceptions=True
            )

            all_chunk_references = []
            all_file_references = []
            all_notes = []
            all_compressed_research = []
            total_tokens = token_usage

            for i, result in enumerate(research_results):
                if isinstance(result, Exception):
                    logger.error(f"Research task {i} failed: {result}")
                    all_notes.append(f"Research task {i} failed: {str(result)}")
                    continue

                chunk_refs = result.get("chunk_references", [])
                file_refs = result.get("file_references", [])
                compressed_research = result.get("compressed_research", "")
                notes = result.get("notes", "")
                tokens = result.get("token_usage", 0)

                all_chunk_references.extend(chunk_refs)
                all_file_references.extend(file_refs)
                all_notes.append(notes)
                all_compressed_research.append(compressed_research)
                total_tokens += tokens

            unique_chunk_refs = list(set(all_chunk_references))
            unique_file_refs = list(set(all_file_references))
            combined_notes = "\n".join(filter(None, all_notes))
            combined_research = "\n\n".join(filter(None, all_compressed_research))

            logger.info(
                f"Research completed: {len(unique_chunk_refs)} chunks, "
                f"{len(unique_file_refs)} files, {total_tokens} tokens"
            )

            return Command(
                goto=END,
                update={
                    "chunk_references": unique_chunk_refs,
                    "file_references": unique_file_refs,
                    "notes": combined_notes,
                    "compressed_research": combined_research,
                    "token_usage": total_tokens,
                },
            )

        except Exception as e:
            logger.error(f"Error in execute_research: {e}", exc_info=True)
            return Command(
                goto=END,
                update={
                    "notes": f"Error during research execution: {str(e)}",
                    "chunk_references": state.get("chunk_references", []),
                    "file_references": state.get("file_references", []),
                    "compressed_research": state.get("compressed_research", ""),
                    "token_usage": token_usage,
                },
            )

    async def supervisor(self, state: SupervisorState):
        """Generate research tasks based on the query"""
        # logger.debug("SupervisorAgent.supervisor called")
        supervisor_messages = state.get("supervisor_messages", [])

        self.research_model = self.llm.bind_tools(self.tools).with_retry(
            stop_after_attempt=self.config.get("max_retries", 3),
        )

        try:
            response = await self.research_model.ainvoke(supervisor_messages)
            return Command(
                goto="execute_research",
                update={
                    "supervisor_messages": supervisor_messages + [response],
                    "token_usage": state.get("token_usage", 0)
                    + response.response_metadata["token_usage"]["total_tokens"],
                },
            )
        except Exception as e:
            logger.error(f"Error in supervisor: {e}", exc_info=True)
            return Command(
                goto=END,
                update={
                    "notes": f"Error in supervisor: {str(e)}",
                    "chunk_references": [],
                    "file_references": [],
                    "compressed_research": "",
                    "token_usage": state.get("token_usage", 0),
                },
            )
