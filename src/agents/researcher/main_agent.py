import uuid
from typing import Any, Optional, Literal
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
    BaseMessage,
)
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command
from pydantic import BaseModel, Field
from src.agents.researcher import prompts
from src.llm.factory import get_llm
from src.agents.researcher.utils import get_current_date
from src.agents.researcher.supervisor_agent import SupervisorAgent
from src.utils.logger_conf import logger
from src.common.streaming import StreamEventBuilder, StreamPhase
from src.config import settings
from src.models.chat import WebSearchConfig


class AgentState(MessagesState):
    """
    AgentState is a state that contains messages and agent-specific data.
    """

    supervisor_messages: list[BaseMessage]
    research_brief: str
    notes: str
    final_report: str
    file_references: list[str]
    chunk_references: list[str]
    compressed_research: str
    need_clarification: bool
    token_usage: int


class AgentInputState(MessagesState):
    """InputState is only 'messages'"""

    folder_context: Optional[str]


class Summary(BaseModel):
    """
    Summary is a model that contains a summary of the research.
    """

    summary: str
    key_excerpts: str


class ResearchAssessment(BaseModel):
    """
    Assessment model for determining whether RAG search is needed or if the request
    can be handled through clarification or direct response.
    """

    message: str = Field(
        description="The response message - clarification question, direct answer, or confirmation of search initiation"
    )

    action: Literal["answer_directly", "search_documents"] = Field(
        description="'answer_directly' for context-based responses or unclear requests, 'search_documents' for RAG search"
    )


class MainAgent:
    """
    MainAgent is the main agent that orchestrates the research process.
    """

    def __init__(self, kb_id: uuid.UUID, config: dict[str, Any]):
        self.config = config
        logger.info(f"Initializing MainAgent with kb_id: {kb_id}")
        self.graph = StateGraph(
            state_schema=AgentState,
            input=AgentInputState,
        )
        self.supervisor = SupervisorAgent(kb_id, config).compile()
        self.graph.add_node("supervisor", self.supervisor)
        self.graph.add_node("final_report_generation", self.final_report_generation)
        self.graph.add_node("research_failure_handler", self.research_failure_handler)
        self.graph.add_node("write_research_brief", self.write_research_brief)
        self.graph.add_node("research_assessment", self.assess_research_need)

        self.graph.add_edge(START, "research_assessment")
        self.graph.add_conditional_edges(
            "supervisor",
            self.should_route_after_research,
            {
                "final_report": "final_report_generation",
                "failure": "research_failure_handler",
            },
        )
        self.graph.add_edge("research_failure_handler", END)
        self.graph.add_edge("final_report_generation", END)

        self.main_agent = self.graph.compile()
        self.llm = get_llm("nxchat")

    def compile(self):
        return self.graph.compile()

    async def should_route_after_research(self, state: AgentState) -> str:
        """Conditional edge to route after research is complete"""
        notes = state.get("notes", "")
        chunk_references = state.get("chunk_references", [])
        file_references = state.get("file_references", [])

        has_results = (
            bool(notes and notes.strip())
            or bool(chunk_references)
            or bool(file_references)
        )

        if has_results:
            logger.info(
                "Research completed with results, routing to final report generation"
            )
            return "final_report"
        else:
            logger.info(
                "Research completed with no results, routing to failure handler"
            )
            return "failure"

    async def research_failure_handler(self, state: AgentState):
        """
        Handle cases where research completely failed with no usable results.
        """
        user_query = state.get("research_brief", "")

        failure_model = self.llm.with_retry(
            stop_after_attempt=self.config.get("max_retries", 3),
        )

        failure_prompt = prompts.research_failure_prompt.format(
            user_query=user_query,
            date=get_current_date(),
        )

        try:
            failure_response = await failure_model.ainvoke(
                [HumanMessage(content=failure_prompt)]
            )
            logger.info("Research failure response generated")
            return {
                "final_report": failure_response.content,
                "messages": [failure_response],
                "chunk_references": [],
                "file_references": [],
                "token_usage": state.get("token_usage", 0)
                + failure_response.response_metadata["token_usage"]["total_tokens"],
            }
        except Exception as e:
            logger.error(f"Error generating failure response: {e}")
            return {
                "final_report": "I apologize, but I was unable to conduct the requested research due to technical difficulties. Please try rephrasing your request or contact support if the issue persists.",
                "messages": [
                    AIMessage(content="Research failed and error handling also failed")
                ],
                "chunk_references": [],
                "file_references": [],
                "token_usage": state.get("token_usage", 0),
            }

    async def generate_response(self, initial_state: AgentInputState) -> dict[str, Any]:
        """
        Generate a response similar to response_agent format.
        This method provides a more focused interface for the final report generation.
        """
        logger.info("Starting response generation")
        final_state = {}

        async for chunk in self.main_agent.astream(initial_state):
            for node_name, node_output in chunk.items():
                if node_name == "write_research_brief":
                    logger.info("Research brief completed. Starting research phase...")

                elif node_name == "supervisor":
                    logger.info("Conducting research and gathering information...")

                elif node_name == "final_report_generation":
                    logger.info("Generating final report...")

                elif node_name == "research_failure_handler":
                    logger.info("Handling research failure...")

            final_state = node_output

        return {
            "final_report": final_state.get("final_report", "No report generated"),
            "messages": final_state.get("messages", []),
            "chunk_references": final_state.get("chunk_references", []),
            "file_references": final_state.get("file_references", []),
            "token_usage": final_state.get("token_usage", 0),
        }

    def generate_streaming_response(self, initial_state: AgentInputState):
        """
        Generate a streaming response similar to response_agent format.
        This method provides a more focused streaming interface for the final report generation.
        """
        logger.info("Starting streaming response generation")

        try:
            compiled_graph = self.compile()
            final_state = {}

            yield StreamEventBuilder.message_start()

            yield StreamEventBuilder.status_update(
                StreamPhase.CONTEXT_ANALYSIS,
                "Starting research process...",
                progress=0.1,
            )

            for chunk in compiled_graph.stream(initial_state):
                for node_name, node_output in chunk.items():
                    if node_name == "write_research_brief":
                        yield StreamEventBuilder.status_update(
                            StreamPhase.CONTEXT_ANALYSIS,
                            "Research brief completed. Starting research phase...",
                            progress=0.3,
                        )

                    elif node_name == "supervisor":
                        yield StreamEventBuilder.status_update(
                            StreamPhase.DOCUMENT_RETRIEVAL,
                            "Conducting research and gathering information...",
                            progress=0.6,
                        )

                    elif node_name == "final_report_generation":
                        yield StreamEventBuilder.status_update(
                            StreamPhase.RESPONSE_GENERATION,
                            "Generating final report...",
                            progress=0.8,
                        )

                final_state = node_output

            if "final_report" not in final_state:
                if final_state.get("need_clarification", False):
                    clarification_message = final_state.get("messages", [])
                    if clarification_message:
                        message_content = clarification_message[-1].content
                        words = message_content.split(" ")
                        for i, word in enumerate(words):
                            yield StreamEventBuilder.content_delta(f"{word} ", index=i)

                yield StreamEventBuilder.message_stop()
                return

            response_model = self.llm.stream(
                [
                    HumanMessage(
                        content=prompts.response_agent_instructions.format(
                            findings="\n".join(
                                final_state.get("final_report", "No findings")
                            ),
                            query=initial_state.get("messages", "No topic provided")[
                                0
                            ].content,
                        )
                    )
                ]
            )

            index = 0
            for chunk in response_model:
                if hasattr(chunk, "content"):
                    yield StreamEventBuilder.content_delta(chunk.content, index=index)
                    index += 1

            yield StreamEventBuilder.status_update(
                StreamPhase.COMPLETE, "Response generation complete", progress=1.0
            )

            references = []
            if final_state:
                chunk_references = final_state.get("chunk_references", [])
                file_references = final_state.get("file_references", [])

                logger.info(
                    f"Processing {len(chunk_references)} chunk references and {len(file_references)} file references"
                )

                for chunk_ref in chunk_references:
                    references.append({"type": "chunk", "data": chunk_ref})

                for file_ref in file_references:
                    references.append({"type": "file", "data": file_ref})
            else:
                logger.warning("No final state found, no references to include")

            metadata = {"search_method": "database_search"}
            if (
                settings.enable_websearch
                and initial_state.get(
                    "web_search", WebSearchConfig(active=False)
                ).active
            ):
                metadata = {"search_method": "web_search"}

            yield StreamEventBuilder.message_stop(
                references=references if references else None,
                metadata=metadata,
            )

            logger.info("Streaming response generation completed successfully")

        except Exception as e:
            logger.exception(f"Error during streaming response generation: {e}")
            yield StreamEventBuilder.error(
                error_type="generation_error",
                message=f"An error occurred while generating the response: {e}",
                code=500,
            )

    async def assess_research_need(self, state: AgentState):
        """
        Determines if RAG search is needed or if the request can be answered from conversation context,
        and handles any necessary clarifications.
        """
        research_router = self.llm.with_structured_output(
            ResearchAssessment, include_raw=True
        ).with_retry(stop_after_attempt=self.config.get("max_retries", 3))
        messages = state["messages"]
        system_message = SystemMessage(
            content=prompts.research_assessment_instructions.format(
                date=get_current_date(),
            )
        )
        messages = [system_message] + messages
        response = await research_router.ainvoke(messages)
        token_usage = response["raw"].response_metadata["token_usage"]["total_tokens"]

        if response["parsed"].action == "search_documents":
            return Command(
                goto="write_research_brief",
                update={
                    "messages": [response["raw"]],
                    "need_clarification": False,
                    "token_usage": token_usage,
                },
            )
        else:
            return Command(
                goto=END,
                update={
                    "messages": [response["raw"]],
                    "need_clarification": True,
                    "token_usage": token_usage,
                },
            )

    async def write_research_brief(self, state: AgentState):
        research_model = self.llm.with_retry(
            stop_after_attempt=self.config.get("max_retries", 3),
        )
        messages = state.get("messages", [])
        token_usage = state.get("token_usage", 0)
        system_message = SystemMessage(
            content=prompts.transform_messages_into_research_topic_prompt
        )
        user_content = HumanMessage(
            content=f"Reformulate the following query, remember to keep the same language as the query: {messages[-1].content}"
        )
        messages = [system_message] + messages[:-1] + [user_content]
        try:
            response = await research_model.ainvoke(messages)
            logger.info(f"Research brief generated: {response.content}")
            return Command(
                goto="supervisor",
                update={
                    "research_brief": response.content,
                    "supervisor_messages": [
                        SystemMessage(content=prompts.lead_researcher_prompt),
                        HumanMessage(content=response.content),
                    ],
                    "token_usage": token_usage
                    + response.response_metadata["token_usage"]["total_tokens"],
                },
            )
        except Exception as e:
            logger.error(f"Error writing research brief: {e}")
            return Command(
                goto=END,
                update={
                    "messages": [
                        AIMessage(content=f"Error writing research brief: {e}")
                    ],
                    "token_usage": token_usage,
                },
            )

    async def final_report_generation(self, state: AgentState):
        notes = state.get("notes", "")
        chunk_references = state.get("chunk_references", [])
        file_references = state.get("file_references", [])
        research_brief = state.get("research_brief", "No research brief generated")
        findings = state.get(
            "compressed_research", "No documents relate to the research topic"
        )
        token_usage = state.get("token_usage", 0)
        final_report_model = self.llm.with_retry(
            stop_after_attempt=self.config.get("max_retries", 3),
        )

        messages = state.get("messages")
        system_message = SystemMessage(
            content=prompts.final_report_generation_system_prompt.format(
                date=get_current_date(),
            )
        )
        human_content_parts = "Please analyze the following information and provide a comprehensive response in the same language as the user query:\n\n"
        if findings:
            human_content_parts += f"<research_findings>\nRetrieved documents and findings from the knowledge base:\n{findings}\n</research_findings>\n"
        if notes:
            human_content_parts += f"<research_notes>\nAdditional analysis notes from document review:\n{notes}\n</research_notes>\n"
        human_content_parts += f"<user_query>\n{research_brief}\n</user_query>\n"
        human_content_parts += (
            "\nRemember to answer in the same language as the user query."
        )
        new_query = HumanMessage(content=human_content_parts)
        messages = [system_message] + messages[:-1] + [new_query]
        try:
            final_report = await final_report_model.ainvoke(messages)
            logger.info(
                f"Final report generated with {len(chunk_references)} chunk references and {len(file_references)} file references"
            )
            return {
                "final_report": final_report.content,
                "messages": [final_report],
                "chunk_references": chunk_references,
                "file_references": file_references,
                "token_usage": token_usage
                + final_report.response_metadata["token_usage"]["total_tokens"],
            }
        except Exception as e:
            logger.error(f"Error generating final report: {e}")
            return {
                "final_report": f"Error generating final report: {e}",
                "messages": [],
                "chunk_references": chunk_references,
                "file_references": file_references,
                "token_usage": token_usage,
            }
