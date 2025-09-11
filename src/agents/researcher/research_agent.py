import json
import uuid
from typing import Any, Optional, cast, List
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
    ToolMessage,
    BaseMessage,
)
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from qdrant_client.models import Filter, models
from typing_extensions import TypedDict
from src.agents.researcher import prompts
from langchain_core.documents import Document
from src.db.repository.document import DocumentRepository
from src.llm.factory import get_llm
from src.models.common import PaginationParams, SearchParams
from src.rag.vector import vector_retrieval
from src.agents.researcher.utils import get_current_date, merge_table_chunks
from src.agents.researcher.tools import SearchFileName, QueryChunks, ResearchCompleted
from langgraph.types import Command
from src.utils.logger_conf import logger


class ResearcherState(TypedDict):
    """
    ResearcherState is a state that contains messages and researcher-specific data.
    """

    # Core conversation and context
    researcher_messages: list[BaseMessage]
    research_topic: str
    folder_context: Optional[str]

    # Iteration control and history
    tool_call_iteration: int
    tool_call_history: dict[str, bool]  # Prevents duplicate tool calls

    # Accumulated results (long-term memory)
    accumulated_findings: str
    notes: str
    file_references: list[str]
    chunk_references: list[str]  # All unique chunk IDs seen so far

    # Per-iteration "scratchpad" (short-term memory)
    tool_results: list[str]
    current_iteration_chunk_ids: list[str]  # Chunk IDs from this iteration only
    document_chunks: list[Document]  # Full documents for citation context
    table_chunks: list[dict]  # Table data for merging

    # Usage tracking
    token_usage: int


class ResearcherInputState(BaseModel):
    """
    ResearcherInputState is a model that contains the input for the researcher.
    """

    researcher_messages: list[BaseMessage]
    research_topic: str
    token_usage: int


class ResearcherOutputState(BaseModel):
    """
    ResearcherOutputState is a model that contains the output of the researcher.
    """

    compressed_research: str
    notes: str
    chunk_references: list[str]
    file_references: list[str]
    token_usage: int


class CitationIteration(BaseModel):
    """CitationIteration is a model that contains the structured output of the citation iteration."""

    indexes: List[int] = Field(
        description="List of document indexes that are relevant for the research topic"
    )
    notes: List[str] = Field(
        description="Key findings and insights extracted from the relevant documents"
    )


class ResearchAgent:
    def __init__(self, kb_id: uuid.UUID, config: dict[str, Any]):
        self.config = config
        logger.info(f"Initializing ResearchAgent with kb_id: {kb_id}")
        self.graph = StateGraph(
            state_schema=ResearcherState,
            input=ResearcherInputState,
            output=ResearcherOutputState,
        )

        self.graph.add_node("research", self.conduct_research)
        self.graph.add_node("execute_search_tools", self.execute_search_tools)
        self.graph.add_node("process_tool_results", self.process_tool_results)
        self.graph.add_node("compress_iteration", self.compress_iteration)
        self.graph.add_node("end_node", self.end_node_func)

        self.graph.add_edge(START, "research")
        self.graph.add_edge("execute_search_tools", "process_tool_results")
        self.graph.add_edge("compress_iteration", "research")
        self.graph.add_edge("end_node", END)

        self.graph.add_conditional_edges(
            "research",
            self.route_after_research,
            {
                "execute_tools": "execute_search_tools",
                "end": "end_node",
            },
        )

        self.llm = get_llm("nxchat")
        self.tools = [SearchFileName, QueryChunks, ResearchCompleted]
        self.document_repository = DocumentRepository()
        self.kb_id = kb_id

    def compile(self):
        return self.graph.compile()

    async def conduct_research(self, state: ResearcherState):
        """Conducts research by calling the LLM with tools."""
        logger.debug("ResearchAgent.conduct_research called")
        researcher_messages = state.get("researcher_messages", [])
        accumulated_findings = state.get("accumulated_findings", "")

        if accumulated_findings:
            context_message = HumanMessage(
                content=(
                    "Did the tool result satisfy the research topic?, "
                    "If not, continue the search but remember to not repeat the same search query."
                    "Else, end the search."
                )
            )
            researcher_messages = researcher_messages + [context_message]

        research_model = self.llm.bind_tools(self.tools).with_retry(
            stop_after_attempt=self.config.get("max_retries", 3),
        )

        try:
            response = await research_model.ainvoke(researcher_messages)
            researcher_messages = researcher_messages + [response]
            return {
                "researcher_messages": researcher_messages,
                "tool_call_iteration": state.get("tool_call_iteration", 0) + 1,
                "token_usage": state.get("token_usage", 0)
                + response.response_metadata["token_usage"]["total_tokens"],
            }
        except Exception as e:
            logger.error(f"Error conducting research: {e}")
            response = AIMessage(content=f"Error conducting research: {e}")
            return {
                "researcher_messages": researcher_messages + [response],
                "tool_call_iteration": state.get("tool_call_iteration", 0) + 1,
                "token_usage": state.get("token_usage", 0),
            }

    async def route_after_research(self, state: ResearcherState) -> str:
        """Routes to either tool execution or final compression based on completion check."""
        logger.debug("ResearchAgent.route_after_research called")

        researcher_messages = state.get("researcher_messages", [])
        if not researcher_messages:
            return "end"

        most_recent_message = cast(AIMessage, researcher_messages[-1])
        if not most_recent_message.tool_calls:
            logger.info("No tool calls found, ending")
            return "end"

        current_iterations = state.get("tool_call_iteration", 0)
        max_iterations_reached = current_iterations >= self.config.get(
            "max_research_iterations", 3
        )

        research_complete = any(
            tool_call["name"] == "ResearchCompleted"
            for tool_call in most_recent_message.tool_calls
        )

        logger.info(
            f"Tool call iterations: {current_iterations}/{self.config.get('max_research_iterations', 3)}, "
            f"Max reached: {max_iterations_reached}, Research complete: {research_complete}"
        )

        if max_iterations_reached or research_complete:
            return "end"

        return "execute_tools"

    async def execute_search_tools(self, state: ResearcherState):
        """Executes search tools (SearchFileName and QueryChunks)."""
        logger.debug("ResearchAgent.execute_search_tools called")

        researcher_messages = state.get("researcher_messages", [])
        most_recent_message = cast(AIMessage, researcher_messages[-1])
        tool_calls = most_recent_message.tool_calls

        tool_results = []
        document_chunks = []
        current_table_chunks = state.get("table_chunks", [])
        current_file_references = state.get("file_references", [])

        current_iteration_chunk_ids = []

        for tool_call in tool_calls:
            if tool_call["name"] == "ResearchCompleted":
                continue

            if tool_call["name"] in ["SearchFileName", "QueryChunks"]:
                tool_call_key = f"{tool_call['name']}_{json.dumps(tool_call['args'], sort_keys=True)}"
                if tool_call_key in state.get("tool_call_history", {}):
                    logger.debug(f"Skipping duplicate tool call {tool_call['id']}")
                    tool_results.append(f"Duplicate {tool_call['name']} call skipped")
                    continue
                state.setdefault("tool_call_history", {})[tool_call_key] = True

            if tool_call["name"] == "SearchFileName":
                logger.info("Executing SearchFileName tool call")
                result, file_refs = await self._execute_search_filename(tool_call)
                tool_results.append(result)
                for ref in file_refs:
                    if ref not in current_file_references:
                        current_file_references.append(ref)

            elif tool_call["name"] == "QueryChunks":
                logger.info("Executing QueryChunks tool call")
                (
                    result,
                    table_chunks,
                    chunk_refs,
                    file_refs,
                    text_only_chunks,
                ) = await self._execute_query_chunks(tool_call, state)
                tool_results.append(result)
                current_table_chunks.extend(table_chunks)
                document_chunks.extend(text_only_chunks)
                for ref in chunk_refs:
                    if ref not in current_iteration_chunk_ids:
                        current_iteration_chunk_ids.append(ref)

                for ref in file_refs:
                    if ref not in current_file_references:
                        current_file_references.append(ref)

        return {
            "tool_results": tool_results,
            "table_chunks": current_table_chunks,
            "file_references": current_file_references,
            "current_iteration_chunk_ids": current_iteration_chunk_ids,
            "document_chunks": document_chunks,
        }

    async def _execute_search_filename(self, tool_call):
        """Execute SearchFileName tool call with comprehensive document information."""
        logger.debug(f"Executing SearchFileName tool call: {tool_call['id']}")

        if not tool_call["args"].get("key"):
            logger.warning(
                f"Skipping SearchFileName tool call {tool_call['id']} - no key"
            )
            return "No search key provided", []

        search_key = tool_call["args"]["key"]
        logger.info(f"Searching for files with key: '{search_key}'")

        result = await self.document_repository.list(
            knowledge_base_id=self.kb_id,
            pagination=PaginationParams(skip=0, limit=100),
            search=SearchParams(query=search_key),
        )

        file_references = [str(doc.id) for doc in result.items]
        logger.info(f"Found {result.total} documents matching '{search_key}'")

        if result.total == 0:
            result = f"No documents found matching '{search_key}'"
        else:
            result_lines = [
                f"Found {result.total} documents matching '{search_key}':\n"
            ]
            for i, doc in enumerate(result.items, 1):
                doc_info = [
                    f"{i}. Document Details:",
                    f"Original Filename: {doc.original_filename}",
                ]
                if doc.description:
                    doc_info.append(f"Description: {doc.description}")
                if doc.processing_error:
                    doc_info.append(f"Processing Error: {doc.processing_error}")
                result_lines.append("\n".join(doc_info))

            result = "\n\n".join(result_lines)

        return result, file_references

    async def _execute_query_chunks(self, tool_call, state):
        """Execute QueryChunks tool call."""
        logger.debug(f"Executing QueryChunks tool call: {tool_call['id']}")

        file_name = tool_call["args"].get("file_name")
        query = tool_call["args"].get("query", "")
        relevant_folder = state.get("folder_context")
        if not query:
            logger.warning(
                f"Skipping QueryChunks tool call {tool_call['id']} - no query"
            )
            return "No query provided", [], [], [], []

        filters: Filter = Filter(must=[])
        if file_name:
            logger.info(f"File name used for filtering: {file_name}")
            cast(list[models.Condition], filters.must).append(
                models.FieldCondition(
                    key="metadata.original_filename",
                    match=models.MatchText(text=file_name),
                )
            )
        if relevant_folder:
            logger.info(f"Folder used for filtering: {relevant_folder}")
            cast(list[models.Condition], filters.must).append(
                models.FieldCondition(
                    key="metadata.folder_path",
                    match=models.MatchAny(any=[relevant_folder]),
                )
            )
        retrieved_docs = await vector_retrieval.retrieve(
            kb_id=str(self.kb_id),
            query=query,
            filters=filters,
            top_k=50,
            top_n=10,
        )

        if len(retrieved_docs) > 10:
            logger.info(f"Retrieved {len(retrieved_docs)} documents, truncating to 10")
            retrieved_docs = retrieved_docs[:10]

        if not retrieved_docs:
            logger.warning(f"No documents found for query: {query}")
            return f"No documents found for query: {query}", [], [], [], []

        return self._process_retrieved_docs(retrieved_docs, query)

    def _process_retrieved_docs(self, retrieved_docs: list[Document], query: str):
        """Process retrieved documents and return formatted result."""
        logger.info(f"Retrieved {len(retrieved_docs)} documents for query: {query}")
        table_chunks = []
        chunk_references = []
        file_references = []
        text_only_chunks = []
        total_length = 0
        threshold = 32_000
        tool_result = "<documents>\n"

        for i, doc in enumerate(retrieved_docs):
            chunk_id = doc.metadata.get("_id")
            if chunk_id and chunk_id not in chunk_references:
                chunk_references.append(str(chunk_id))

            file_id = doc.metadata.get("document_id")
            if file_id and file_id not in file_references:
                file_references.append(str(file_id))

            sheet_name = doc.metadata.get("sheet_name")
            page_content = doc.page_content

            if sheet_name and sheet_name != "N/A":
                table_chunks.append(
                    {
                        "metadata": doc.metadata,
                        "page_content": page_content,
                    }
                )
                # logger.debug(f"Stored table chunk from sheet: {sheet_name}")
            else:
                text_only_chunks.append(doc)
            tool_result += f'  <document index="{i + 1}">\n'
            metadata = getattr(doc, "metadata", {})
            source = metadata.get("original_filename", f"Document {i + 1}")
            folder_path = metadata.get("folder_path", "")
            if folder_path:
                tool_result += f"<folder_path>{folder_path}</folder_path>\n"
            tool_result += f"<source>{source}</source>\n"
            tool_result += "<document_content>\n"
            tool_result += f"{page_content}"
            tool_result += "</document_content>\n"
            tool_result += "</document>\n"
            tool_result += "\n"
            total_length += len(page_content)
            if total_length + len(page_content) > threshold:
                logger.warning(
                    f"Total length of documents exceeds threshold: {total_length}"
                )
                break

        tool_result += "</documents>"
        if table_chunks:
            tool_result += f"\n\n[Note: {len(table_chunks)} table chunks stored separately for merging during compression]"
            logger.info(f"Stored {len(table_chunks)} table chunks separately")

        return (
            tool_result,
            table_chunks,
            chunk_references,
            file_references,
            text_only_chunks,
        )

    async def process_tool_results(self, state: ResearcherState):
        """Processes tool results and updates state."""
        logger.debug("ResearchAgent.process_tool_results called")
        researcher_messages = state.get("researcher_messages", [])
        current_iteration_chunks = state.get("current_iteration_chunk_ids", [])
        most_recent_message = cast(AIMessage, researcher_messages[-1])
        tool_results = state.get("tool_results", [])

        relevant_tool_calls = [
            tool_call
            for tool_call in most_recent_message.tool_calls
            if tool_call["name"] != "ResearchCompleted"
        ]

        tool_outputs = []
        for i, tool_call in enumerate(relevant_tool_calls):
            if i >= len(tool_results):
                print(f"Warning: Missing result for tool call {i}: {tool_call['name']}")
                break

            tool_outputs.append(
                ToolMessage(
                    content=tool_results[i],
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"],
                )
            )

        tool_call_iteration = state.get("tool_call_iteration", 0)
        if tool_call_iteration > 1:
            novelty_threshold = self.config.get("novelty_threshold", 0.5)
            all_previous_chunks = state.get("chunk_references", [])

            novelty_check_passed = True
            if current_iteration_chunks:
                previous_chunks_set = set(all_previous_chunks)
                new_chunks = [
                    chunk
                    for chunk in current_iteration_chunks
                    if chunk not in previous_chunks_set
                ]
                novelty_ratio = len(new_chunks) / len(current_iteration_chunks)
                novelty_check_passed = novelty_ratio >= novelty_threshold
                logger.info(
                    f"Novelty check: {len(new_chunks)}/{len(current_iteration_chunks)} = {novelty_ratio:.2f} (threshold: {novelty_threshold})"
                )
                updated_chunk_references = all_previous_chunks.copy()
                for chunk_id in current_iteration_chunks:
                    if chunk_id not in updated_chunk_references:
                        updated_chunk_references.append(chunk_id)
            else:
                logger.info("No current iteration chunks to check for novelty")
                updated_chunk_references = all_previous_chunks

            if not novelty_check_passed:
                logger.info("Novelty check failed, ending research")
                return Command(goto="end")
        else:
            updated_chunk_references = state.get("chunk_references", []).copy()
            for chunk_id in current_iteration_chunks:
                if chunk_id not in updated_chunk_references:
                    updated_chunk_references.append(chunk_id)

        return Command(
            goto="compress_iteration",
            update={
                "researcher_messages": researcher_messages + tool_outputs,
                "chunk_references": updated_chunk_references,
            },
        )

    async def compress_iteration(self, state: ResearcherState):
        """Compresses current iteration findings and merges with accumulated findings."""
        logger.debug("ResearchAgent.compress_iteration called")
        document_chunks = state.get("document_chunks", [])
        accumulated_findings = state.get("accumulated_findings", "")
        table_chunks = state.get("table_chunks", [])
        iteration = state.get("tool_call_iteration", 0)
        research_topic = state.get("research_topic", "")
        token_usage = state.get("token_usage", 0)
        tables_content = ""
        table_compress_response = ""

        if table_chunks:
            logger.info(
                f"Processing {len(table_chunks)} table chunks for iteration {iteration}"
            )
            merged_tables = merge_table_chunks(table_chunks)
            if merged_tables:
                logger.info("Compressing merged tables")
                tables_content = "\n".join(merged_tables)
                table_messages = [
                    SystemMessage(
                        content=prompts.compress_research_table_system_prompt.format(
                            date=get_current_date()
                        )
                    ),
                    HumanMessage(
                        content=f"Here are the merged table data from all retrieved table chunks. Each table includes its sheet name as a header, and the table content in markdown format:\n\n{tables_content}\n\nUser query: {research_topic}. Remember to answer in the same language as the user query."
                    ),
                ]

                table_compress_model = self.llm.with_retry(
                    stop_after_attempt=self.config.get("max_retries", 3),
                )
                try:
                    table_compress_response = await table_compress_model.ainvoke(
                        table_messages
                    )
                    tables_contents = table_compress_response.content
                except Exception as e:
                    logger.error(f"Error compressing table chunks: {e}")
                    tables_contents = ""
            accumulated_findings += tables_contents
            token_usage += table_compress_response.response_metadata["token_usage"][
                "total_tokens"
            ]

        if not document_chunks:
            logger.info("No document chunks to compress")
            return {
                "accumulated_findings": accumulated_findings,
                "token_usage": token_usage,
                "table_chunks": [],
            }

        human_content_parts = "Please analyze the following information and provide high accurate citations and notes:\n\n"
        if document_chunks:
            research_findings = self._format_context_for_response(document_chunks)
            human_content_parts += (
                f"<research_findings>\n{research_findings}\n</research_findings>\n"
            )
        if research_topic:
            logger.info(f"Research topic: {research_topic}")
            human_content_parts += f"<user_query>\n{research_topic}\n</user_query>\n"
        human_content_parts += "\nRemember to cite correctly, provide notes in the same language as the research topic and return in correct json format."

        compression_messages = [
            SystemMessage(content=prompts.citation_iteration_system_prompt),
            HumanMessage(content=human_content_parts),
        ]

        compression_model = self.llm.with_structured_output(
            CitationIteration, include_raw=True
        ).with_retry(
            stop_after_attempt=self.config.get("max_retries", 3),
        )

        try:
            response = await compression_model.ainvoke(compression_messages)
            citation_indexes = response["parsed"].indexes
            if citation_indexes:
                cited_docs = [
                    document_chunks[i - 1]
                    for i in citation_indexes
                    if 0 < i <= len(document_chunks)
                ]
                cited_docs_content = self._format_context_for_response(cited_docs)
                accumulated_findings += cited_docs_content + "\n"

            current_notes = state.get("notes", "")
            iteration_notes_list = response["parsed"].notes
            iteration_notes_str = ""
            if iteration_notes_list:
                logger.info(
                    f"Compressed iteration {iteration} findings. Added {len(iteration_notes_list)} notes."
                )
                iteration_notes_str = "\n".join(iteration_notes_list)

            updated_notes = (
                current_notes + "\n" + iteration_notes_str
                if current_notes and iteration_notes_str
                else current_notes + iteration_notes_str
            )

            return {
                "accumulated_findings": accumulated_findings,
                "notes": updated_notes,
                "token_usage": token_usage
                + response["raw"].response_metadata["token_usage"]["total_tokens"],
                "table_chunks": [],
                "document_chunks": [],
            }

        except Exception as e:
            logger.error(f"Error compressing iteration findings: {e}")
            current_notes = state.get("notes", "")
            error_note = f"Iteration {iteration}: Compression failed - {str(e)}"
            return {
                "accumulated_findings": accumulated_findings,
                "notes": current_notes + error_note,
                "token_usage": state.get("token_usage", 0),
                "table_chunks": [],
                "document_chunks": [],
            }

    async def end_node_func(self, state: ResearcherState):
        """Ends the research process and prepares final output."""
        logger.debug("ResearchAgent.end called")
        return {
            "compressed_research": state.get("accumulated_findings", ""),
            "notes": state.get("notes", ""),
            "chunk_references": state.get("chunk_references", []),
            "file_references": state.get("file_references", []),
            "token_usage": state.get("token_usage", 0),
        }

    def _format_context_for_response(self, documents: List[Document]) -> str:
        """Formats documents for the response prompt."""
        if not documents:
            return "<documents>No relevant documents found.</documents>"

        xml_output = "<documents>\n"

        for i, doc in enumerate(documents):
            xml_output += f'  <document index="{i + 1}">\n'
            metadata = getattr(doc, "metadata", {})
            source = metadata.get("original_filename", f"Document {i + 1}")
            folder_path = metadata.get("folder_path", "")
            sheet_name = metadata.get("sheet_name", "")
            xml_output += f"<source>{source}</source>\n"
            if folder_path:
                xml_output += f"<folder_path>{folder_path}</folder_path>\n"
            if sheet_name:
                xml_output += f"<sheet_name>{sheet_name}</sheet_name>\n"
            content = getattr(doc, "page_content", "")
            xml_output += "<document_content>\n"
            xml_output += f"{content}\n"
            xml_output += "</document_content>\n"
            xml_output += "</document>\n"
        xml_output += "</documents>"

        return xml_output
