import json
from typing import Dict, Any, List, Optional
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from src.agents.basic import citation_agent, compress_agent
from src.agents.tools.server.mcp_retrieve_tools import rag_search, web_search, think
from src.utils.logger_conf import logger
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from src.agents.graph.state import SearchResult, ResearchState, SearchQuery
from src.agents.graph.prompts import PromptTemplates
from src.agents.graph.schemas import (
    SearchPlanSchema,
    VerificationSchema,
    DynamicQueriesSchema,
    ReflectionSchema,
)
from src.llm.factory import get_llm
from src.agents.basic.base import AgentBase
from src.utils import parse_response


class ResearchGraph(AgentBase):
    """Research Subgraph - Deep research with iterative search loop"""

    def __init__(self):
        self.llm = get_llm("nxchat")
        self.thinking_llm = self.llm.bind_tools([think])
        self.graph = self._build_graph()
        self.max_searches = 20
        self.max_consecutive_failures = 3
        logger.info("ResearchGraph initialized successfully.")

    async def query_planner_node(self, state: ResearchState) -> Dict[str, Any]:
        """Create research plan"""
        max_iterations = 5
        system_prompt = SystemMessage(content=PromptTemplates.QUERY_PLANNER_PROMPT)
        prompt = HumanMessage(
            content=f"Create the plan for the following query: {state['contextualized_query']}"
        )
        messages: List[BaseMessage] = [system_prompt] + [prompt]

        query_planner_llm = self.thinking_llm
        response = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=query_planner_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_planner_response,
            retry_prompt="Please provide the research plan in correct JSON format.",
        )

        if not response or not response.get("queries"):
            logger.error(
                "[QueryPlanner] Failed to generate a valid search plan or plan is empty."
            )
            return {
                "pending_queries": [],
                "accumulated_knowledge": "",
                "completed_queries": [],
                "max_searches": self.max_searches,
                "iteration_count": 0,
                "all_search_history": [],
                "used_rag_ids": [],
                "used_web_urls": [],
                "has_tried_rag": False,
                "has_tried_web": False,
                "consecutive_search_failures": 0,
                "citation_counter": 0,
                "cited_documents": [],
                "rag_is_unavailable": False,
                "web_is_unavailable": False,
                "should_retry_query": False,
            }

        queries = response.get("queries", [])
        all_queries: List[SearchQuery] = queries
        all_queries.sort(key=lambda x: x.get("priority", 0), reverse=True)

        return {
            "pending_queries": all_queries,
            "completed_queries": [],
            "max_searches": self.max_searches,
            "iteration_count": 0,
            "accumulated_knowledge": "",
            "all_search_history": [],
            "used_rag_ids": [],
            "used_web_urls": [],
            "has_tried_rag": False,
            "has_tried_web": False,
            "consecutive_search_failures": 0,
            "citation_counter": 0,
            "cited_documents": [],
            "rag_is_unavailable": False,
            "web_is_unavailable": False,
            "should_retry_query": False,
        }

    def decide_after_planner(self, state: ResearchState) -> str:
        """Decides where to go after the query planner."""
        if state.get("pending_queries"):
            logger.info("[Router] Plan generated. Proceeding to search_executor.")
            return "pre_flight_rag_check"
        else:
            logger.warning("[Router] No plan generated. Proceeding to handle_no_plan.")
            return "handle_no_plan"

    async def pre_flight_rag_check_node(self, state: ResearchState) -> Dict[str, Any]:
        """
        Performs a single RAG check with the main query to determine if the
        entire RAG source is relevant for this session using the citation agent.
        """
        original_query = state["contextualized_query"]
        context_metadata = state["context_metadata"]

        have_rag_search_type = any(
            query["search_type"] == "rag" for query in state["pending_queries"]
        )
        if not have_rag_search_type:
            return {"is_rag_source_relevant": True}

        try:
            documents = await rag_search(
                query=original_query, context_metadata=context_metadata
            )

            if not documents:
                logger.warning(
                    "[PreFlightCheck] RAG source returned no documents. Deeming irrelevant."
                )
                return {"is_rag_source_relevant": False, "rag_is_unavailable": True}

            relevant_indices = await citation_agent.ainvoke(
                history=[HumanMessage(content=original_query)], reference=documents
            )

            if not relevant_indices or not relevant_indices.indexes:
                logger.warning(
                    "[PreFlightCheck] Citation agent found no relevant documents in initial RAG search. Deeming RAG source irrelevant for this run."
                )
                return {"is_rag_source_relevant": False, "rag_is_unavailable": True}

        except Exception as e:
            logger.error(
                f"[PreFlightCheck] RAG pre-flight check failed with an error: {e}. Disabling RAG."
            )
            return {"is_rag_source_relevant": False, "rag_is_unavailable": True}

        return {"is_rag_source_relevant": True}

    async def handle_no_plan_node(self, state: ResearchState) -> Dict[str, Any]:
        """
        Prepares the state to go directly to the dynamic query generator
        if the initial planner fails.
        """
        verification_result = {
            "is_sufficient": False,
            "missing_aspects": [state["contextualized_query"]],
            "confidence": "low",
        }
        return {"verification_result": verification_result}

    async def search_executor_node(self, state: ResearchState) -> Dict[str, Any]:
        """Execute search query with robust failure handling"""
        if not state["pending_queries"]:
            logger.warning("[SearchExecutor] No pending queries. Skipping execution.")
            return {}

        current_query = state["pending_queries"][0]
        remaining_queries = state["pending_queries"][1:]

        search_type = current_query["search_type"]
        query_text = current_query["query"]
        context_metadata = state["context_metadata"]

        rag_unavailable = state.get("rag_is_unavailable", False)
        web_unavailable = state.get("web_is_unavailable", False)

        is_rag_relevant = state.get("is_rag_source_relevant", True)
        if search_type == "rag" and not is_rag_relevant:
            logger.warning(
                f"[SearchExecutor] RAG source deemed irrelevant by pre-flight check. Attempting to switch query '{query_text}' to Web."
            )
            if not web_unavailable:
                search_type = "web"
                current_query["search_type"] = "web"
            else:
                logger.error(
                    "[SearchExecutor] RAG source is irrelevant and Web is also unavailable. Terminating this query."
                )
                return {
                    "completed_queries": state["completed_queries"] + [current_query],
                    "pending_queries": remaining_queries,
                    "consecutive_search_failures": state.get(
                        "consecutive_search_failures", 0
                    )
                    + 1,
                }

        if search_type == "rag" and rag_unavailable:
            logger.warning(
                f"[SearchExecutor] RAG is unavailable, attempting to switch query '{query_text}' to Web."
            )
            if not web_unavailable:
                search_type = "web"
                current_query["search_type"] = "web"
            else:
                logger.error(
                    "[SearchExecutor] Both RAG and Web are unavailable. Terminating."
                )
                return {
                    "completed_queries": state["completed_queries"] + [current_query],
                    "pending_queries": remaining_queries,
                    "consecutive_search_failures": self.max_consecutive_failures,
                }

        if search_type == "web" and web_unavailable:
            logger.warning(
                f"[SearchExecutor] Web is unavailable, attempting to switch query '{query_text}' to RAG."
            )
            if not rag_unavailable:
                search_type = "rag"
                current_query["search_type"] = "rag"
            else:
                logger.error(
                    "[SearchExecutor] Both Web and RAG are unavailable. Terminating."
                )
                return {
                    "completed_queries": state["completed_queries"] + [current_query],
                    "pending_queries": remaining_queries,
                    "consecutive_search_failures": self.max_consecutive_failures,
                }

        documents = []
        try:
            if search_type == "rag":
                documents = await rag_search(
                    query=query_text, context_metadata=context_metadata
                )
            else:  # web
                documents = await web_search(
                    query=query_text,
                )
            consecutive_search_failures = 0
        except Exception as e:
            logger.error(
                f"[SearchExecutor] HARD FAILURE in {search_type.upper()} search for '{query_text}'. Error: {e}"
            )
            consecutive_search_failures = (
                state.get("consecutive_search_failures", 0) + 1
            )
            new_pending_queries = list(remaining_queries)
            fallback_type = ""
            updated_state = {
                "rag_is_unavailable": rag_unavailable,
                "web_is_unavailable": web_unavailable,
            }

            if search_type == "rag":
                updated_state["rag_is_unavailable"] = True
                if not web_unavailable:
                    fallback_type = "web"
            else:  # web
                updated_state["web_is_unavailable"] = True
                if not rag_unavailable:
                    fallback_type = "rag"

            if fallback_type:
                logger.warning(
                    f"[SearchExecutor] Switching all future '{search_type}' queries to '{fallback_type}'."
                )
                for i in range(len(new_pending_queries)):
                    if new_pending_queries[i]["search_type"] == search_type:
                        new_pending_queries[i]["search_type"] = fallback_type

            return {
                "completed_queries": state["completed_queries"] + [current_query],
                "pending_queries": new_pending_queries,
                "iteration_count": state["iteration_count"] + 1,
                "consecutive_search_failures": consecutive_search_failures,
                "rag_is_unavailable": updated_state["rag_is_unavailable"],
                "web_is_unavailable": updated_state["web_is_unavailable"],
            }

        search_result = SearchResult(
            query=query_text,
            documents=documents,
            search_type=search_type,
            processed=False,
        )

        return {
            "search_results": search_result,
            "completed_queries": state["completed_queries"] + [current_query],
            "pending_queries": remaining_queries,
            "all_search_history": state["all_search_history"] + [search_result],
            "iteration_count": state["iteration_count"] + 1,
            "has_tried_rag": state.get("has_tried_rag", False) or search_type == "rag",
            "has_tried_web": state.get("has_tried_web", False) or search_type == "web",
            "consecutive_search_failures": consecutive_search_failures,
        }

    async def process_results_node(self, state: ResearchState) -> Dict[str, Any]:
        """Filter, compress, merge results with hybrid strategy"""
        if not state.get("search_results") or not state["search_results"].get(
            "documents"
        ):
            logger.warning("[ProcessResults] No documents found in search result.")
            return {"should_retry_query": True, "search_results": {}}

        overlap_threshold = 0.5

        documents = state["search_results"]["documents"]
        search_type = state["search_results"]["search_type"]
        current_query = state["search_results"]["query"]

        if search_type == "web":
            source_ids = [
                doc.metadata.get("original_filename", "") for doc in documents
            ]
            new_documents = [
                doc
                for doc in documents
                if doc.metadata.get("original_filename", "")
                not in state["used_web_urls"]
            ]
            overlap = set(source_ids) & set(state["used_web_urls"])
            ratio = len(overlap) / max(len(source_ids), 1)
            if ratio > overlap_threshold:
                logger.warning(
                    f"[ProcessResults] High web source overlap ({ratio:.1%}). Switching to RAG."
                )
                return {"should_retry_query": True}
        else:
            source_ids = [doc.metadata.get("document_id", "") for doc in documents]
            new_documents = [
                doc
                for doc in documents
                if doc.metadata.get("document_id", "") not in state["used_rag_ids"]
            ]
            overlap = set(source_ids) & set(state["used_rag_ids"])
            ratio = len(overlap) / max(len(source_ids), 1)
            if ratio > overlap_threshold:
                logger.warning(
                    f"[ProcessResults] High RAG source overlap ({ratio:.1%}). Switching to Web."
                )
                return {"should_retry_query": True}

        if not new_documents:
            logger.warning(
                "[ProcessResults] All documents already used. Switching search type."
            )
            return {"should_retry_query": True}

        relevant_indices = await citation_agent.ainvoke(
            history=[HumanMessage(content=current_query)], reference=new_documents
        )

        if not relevant_indices or not relevant_indices.indexes:
            logger.warning(
                "[ProcessResults] Citation agent found no relevant documents. This is a soft failure."
            )
            return {"should_retry_query": True}

        cited_docs = [
            new_documents[i - 1]
            for i in relevant_indices.indexes
            if 0 < i <= len(new_documents)
        ]

        citation_start_index = state.get("citation_counter", 0)
        all_cited_docs_so_far = state.get("cited_documents", [])

        docs_with_citation_markers = []
        current_citation_index = citation_start_index

        for doc in cited_docs:
            doc_copy = doc.model_copy(deep=True)
            doc_copy.page_content = (
                f"[CITATION: {current_citation_index}] {doc.page_content}"
            )
            docs_with_citation_markers.append(doc_copy)
            all_cited_docs_so_far.append(doc)
            current_citation_index += 1

        accumulated_len = len(state["accumulated_knowledge"])

        should_consolidate = ratio > overlap_threshold * 0.5 or accumulated_len > 10000

        if should_consolidate and state["accumulated_knowledge"]:
            new_merged = await compress_agent.ainvoke_with_merge(
                query=current_query,
                new_documents=docs_with_citation_markers,
                existing_knowledge=state["accumulated_knowledge"],
            )
            merged = new_merged if new_merged else state["accumulated_knowledge"]
        else:
            compressed = await compress_agent.ainvoke(
                query=current_query, reference=docs_with_citation_markers
            )

            if state["accumulated_knowledge"]:
                merged = (
                    f"{state['accumulated_knowledge']}\n\n"
                    f"## {current_query}\n\n{compressed}"
                )
            else:
                merged = compressed

        new_rag_ids = state["used_rag_ids"]
        new_web_urls = state["used_web_urls"]

        if search_type == "rag":
            new_rag_ids = list(set(state["used_rag_ids"] + source_ids))
        else:
            new_web_urls = list(set(state["used_web_urls"] + source_ids))

        last_search_result = state["search_results"]
        last_search_result["processed"] = True
        all_search_history = state["all_search_history"][:-1] + [last_search_result]

        return {
            "accumulated_knowledge": merged,
            "used_rag_ids": new_rag_ids,
            "used_web_urls": new_web_urls,
            "search_results": last_search_result,
            "all_search_history": all_search_history,
            "should_retry_query": False,
            "citation_counter": current_citation_index,
            "cited_documents": all_cited_docs_so_far,
        }

    def decide_after_processing(self, state: ResearchState) -> str:
        """
        Decides the next step after processing search results.
        - If successful, go to verification.
        - If soft failure, try to retry with a fallback search type IF AVAILABLE.
        - If fallback is unavailable, skip the failed query and continue.
        """
        if not state.get("should_retry_query"):
            return "verification_agent"

        logger.warning(
            "[Router] Soft failure detected. Evaluating retry for the last query."
        )

        last_query = state["completed_queries"][-1]
        last_search_type = last_query["search_type"]
        fallback_type = "web" if last_search_type == "rag" else "rag"

        is_fallback_usable = True
        if fallback_type == "rag":
            if state.get("rag_is_unavailable") or not state.get(
                "is_rag_source_relevant", True
            ):
                is_fallback_usable = False
                logger.warning(
                    "[Router] Cannot retry with RAG because it's unavailable or deemed irrelevant."
                )
        elif fallback_type == "web":
            if state.get("web_is_unavailable"):
                is_fallback_usable = False
                logger.warning(
                    "[Router] Cannot retry with Web because it's unavailable."
                )

        if not is_fallback_usable:
            logger.warning(
                f"[Router] Fallback type '{fallback_type.upper()}' is not usable for query '{last_query['query']}'. "
                "Skipping this retry attempt and moving on."
            )
            if state.get("pending_queries"):
                return "search_executor"
            else:
                return "verification_agent"
        else:
            logger.info(f"[Router] Retrying query with {fallback_type.upper()}.")
            retry_query = last_query.copy()
            retry_query["search_type"] = fallback_type

            pending = state.get("pending_queries", [])
            pending.insert(0, retry_query)
            state["pending_queries"] = pending

            state["should_retry_query"] = False

            return "search_executor"

    async def verification_agent_node(self, state: ResearchState) -> Dict[str, Any]:
        """Verify sufficiency"""
        if not state.get("accumulated_knowledge"):
            logger.warning(
                "[Verification] No accumulated knowledge to verify. Defaulting to insufficient."
            )
            return {
                "verification_result": {
                    "is_sufficient": False,
                    "missing_aspects": [state["contextualized_query"]],
                    "confidence": "low",
                }
            }

        max_iterations = 3

        prompt_input = PromptTemplates.VERIFICATION_HUMAN_PROMPT.format(
            original_query=state["contextualized_query"],
            accumulated_knowledge=state["accumulated_knowledge"],
        )

        messages: List[BaseMessage] = [
            SystemMessage(content=PromptTemplates.VERIFICATION_PROMPT),
            HumanMessage(content=prompt_input),
        ]

        verification_llm = self.thinking_llm
        verification_dict = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=verification_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_verification_response,
            retry_prompt="Please provide the verification result in correct JSON format.",
        )

        if not verification_dict:
            logger.error(
                "[Verification] Failed to get a valid verification. Defaulting to insufficient."
            )
            return {
                "verification_result": {
                    "is_sufficient": False,
                    "missing_aspects": [],
                    "confidence": "low",
                }
            }

        return {"verification_result": verification_dict}

    async def reflection_node(self, state: ResearchState) -> Dict[str, Any]:
        """
        Critiques the current research state and suggests next steps.
        """

        search_history_str = json.dumps(state.get("all_search_history", []), indent=2)

        prompt_input = PromptTemplates.REFLECTION_HUMAN_PROMPT.format(
            original_query=state["contextualized_query"],
            accumulated_knowledge=state["accumulated_knowledge"],
            missing_aspects=json.dumps(state["verification_result"]["missing_aspects"]),
            search_history=search_history_str,
        )

        messages: List[BaseMessage] = [
            SystemMessage(content=PromptTemplates.REFLECTION_PROMPT),
            HumanMessage(content=prompt_input),
        ]

        reflection_llm = self.thinking_llm
        reflection_result = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=reflection_llm,
            available_tools={"think": think},
            max_iterations=3,
            parse_fn=parse_reflection_response,
            retry_prompt="Please provide the reflection in the correct JSON format.",
        )

        if not reflection_result:
            logger.error("[Reflection] Failed to generate a valid reflection.")
            return {"reflection_result": {"critique": "N/A", "next_steps": "N/A"}}

        return {"reflection_result": reflection_result}

    async def dynamic_query_generator_node(
        self, state: ResearchState
    ) -> Dict[str, Any]:
        """Generate dynamic queries with search history awareness"""

        max_iterations = 3
        verification = state["verification_result"]

        if not verification or not verification.get("missing_aspects"):
            logger.warning(
                "[DynamicQueryGenerator] No missing aspects identified. Skipping query generation."
            )
            return {"pending_queries": []}

        missing_aspects = verification["missing_aspects"]

        search_history = []
        for search_result in state.get("all_search_history", []):
            search_history.append(
                {
                    "query": search_result["query"],
                    "search_type": search_result["search_type"],
                }
            )

        search_history_str = (
            json.dumps(search_history, indent=2)
            if search_history
            else "No previous searches"
        )

        reflection = state.get(
            "reflection_result", {"critique": "N/A", "next_steps": "N/A"}
        )
        reflection_str = f"Critique: {reflection['critique']}\nSuggested Next Steps: {reflection['next_steps']}"

        prompt_input = PromptTemplates.DYNAMIC_QUERY_GENERATOR_HUMAN_PROMPT.format(
            original_query=state["contextualized_query"],
            accumulated_knowledge=state["accumulated_knowledge"],
            missing_aspects=json.dumps(missing_aspects, indent=2),
            search_history=search_history_str,
            reflection=reflection_str,
        )

        messages: List[BaseMessage] = [
            SystemMessage(content=PromptTemplates.DYNAMIC_QUERY_GENERATOR_PROMPT),
            HumanMessage(content=prompt_input),
        ]

        dynamic_query_generator_llm = self.thinking_llm
        dynamic_query_generator_dict = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=dynamic_query_generator_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_dynamic_query_generator_response,
            retry_prompt="Please provide the dynamic query generator result in correct JSON format.",
        )

        if not dynamic_query_generator_dict:
            logger.error(
                "[DynamicQueryGenerator] Failed to generate valid dynamic queries."
            )
            return {"pending_queries": []}

        new_queries = dynamic_query_generator_dict.get("queries", [])

        if not new_queries:
            logger.warning(
                "[DynamicQueryGenerator] Agent returned empty queries. This may mean information gaps are minor or unresolvable."
            )
            return {"pending_queries": []}

        return {"pending_queries": new_queries}

    def route_after_dynamic_generation(self, state: ResearchState) -> str:
        """Decides where to go after attempting to generate new queries."""
        if state.get("pending_queries"):
            logger.info(
                "[Router] New queries generated. Proceeding to search_executor."
            )
            return "search_executor"
        else:
            logger.error(
                "[Router] Failed to generate new queries. Terminating process."
            )
            return "__end__"

    def route_after_verification(self, state: ResearchState) -> str:
        """Smart routing based on verification + pending queries analysis"""
        iteration = state["iteration_count"]
        max_searches = state["max_searches"]

        if state.get("consecutive_search_failures", 0) >= self.max_consecutive_failures:
            logger.error(
                f"[Router] Route: Exceeded max consecutive search failures ({self.max_consecutive_failures}) → END"
            )
            return "__end__"

        if iteration >= max_searches:
            logger.info("[Router] Route: Max iterations reached → END")
            return "__end__"

        verification = state["verification_result"]
        if not verification:
            logger.warning("[Router] Route: No verification result → END")
            return "__end__"

        if verification.get("is_sufficient"):
            logger.info(
                f"[Router] Knowledge is sufficient (confidence: {verification.get('confidence')}). Ending."
            )
            return "__end__"

        if state.get("pending_queries"):
            logger.info(
                "[Router] Pending queries exist. Continuing with planned search."
            )
            return "search_executor"

        return "reflection_node"

    def _build_graph(self) -> CompiledStateGraph:
        """Build research graph"""
        workflow = StateGraph(ResearchState)

        workflow.add_node("query_planner", self.query_planner_node)
        workflow.add_node("pre_flight_rag_check", self.pre_flight_rag_check_node)
        workflow.add_node("search_executor", self.search_executor_node)
        workflow.add_node("process_results", self.process_results_node)
        workflow.add_node("verification_agent", self.verification_agent_node)
        workflow.add_node("dynamic_query_generator", self.dynamic_query_generator_node)
        workflow.add_node("handle_no_plan", self.handle_no_plan_node)
        workflow.add_node("reflection_node", self.reflection_node)

        workflow.set_entry_point("query_planner")

        workflow.add_conditional_edges(
            "query_planner",
            self.decide_after_planner,
            {
                "pre_flight_rag_check": "pre_flight_rag_check",
                "handle_no_plan": "handle_no_plan",
            },
        )

        workflow.add_edge("pre_flight_rag_check", "search_executor")
        workflow.add_edge("handle_no_plan", "dynamic_query_generator")
        workflow.add_edge("search_executor", "process_results")

        workflow.add_conditional_edges(
            "process_results",
            self.decide_after_processing,
            {
                "search_executor": "search_executor",
                "verification_agent": "verification_agent",
            },
        )

        workflow.add_edge("reflection_node", "dynamic_query_generator")

        workflow.add_conditional_edges(
            "dynamic_query_generator",
            self.route_after_dynamic_generation,
            {
                "search_executor": "search_executor",
                "__end__": END,
            },
        )

        workflow.add_conditional_edges(
            "verification_agent",
            self.route_after_verification,
            {
                "search_executor": "search_executor",
                "reflection_node": "reflection_node",
                "__end__": END,
            },
        )

        return workflow.compile()

    async def run(self, state: ResearchState) -> ResearchState:
        """Run research graph"""
        logger.info(
            f"--- Running ResearchGraph for query: '{state.get('contextualized_query')}' ---"
        )
        config = {"recursion_limit": 100}
        result = await self.graph.ainvoke(state, config=config)

        accumulated_knowledge = result.get("accumulated_knowledge", "")

        if not accumulated_knowledge:
            logger.warning(
                "--- ResearchGraph finished, but NO KNOWLEDGE was accumulated. The research process may have failed or found no relevant information. ---"
            )
        else:
            logger.info(
                f"--- ResearchGraph finished. Final knowledge length: {len(accumulated_knowledge)} chars. ---\n\n"
            )
        return result


def parse_planner_response(content: str) -> Optional[SearchPlanSchema]:
    """Parse planner response"""
    try:
        parsed = parse_response(content)
        if not parsed:
            logger.warning("[Parser] Failed to parse planner response (null result).")
            return None
        response = SearchPlanSchema(**parsed)
        dumped = response.model_dump()
        return dumped
    except Exception as e:
        logger.error(f"[Parser] Error parsing planner response: {e}", exc_info=True)
        return None


def parse_verification_response(content: str) -> Optional[VerificationSchema]:
    """Parse verification response"""
    try:
        parsed = parse_response(content)
        if not parsed:
            logger.warning(
                "[Parser] Failed to parse verification response (null result)."
            )
            return None
        response = VerificationSchema(**parsed)
        dumped = response.model_dump()
        return dumped
    except Exception as e:
        logger.error(
            f"[Parser] Error parsing verification response: {e}", exc_info=True
        )
        return None


def parse_dynamic_query_generator_response(
    content: str,
) -> Optional[DynamicQueriesSchema]:
    """Parse dynamic query generator response"""
    try:
        parsed = parse_response(content)
        if not parsed:
            logger.warning(
                "[Parser] Failed to parse dynamic query generator response (null result)."
            )
            return None
        response = DynamicQueriesSchema(**parsed)
        dumped = response.model_dump()
        return dumped
    except Exception as e:
        logger.error(
            f"[Parser] Error parsing dynamic query generator response: {e}",
            exc_info=True,
        )
        return None


def parse_reflection_response(content: str) -> Optional[ReflectionSchema]:
    """Parse reflection response"""
    try:
        parsed = parse_response(content)
        if not parsed:
            logger.warning(
                "[Parser] Failed to parse reflection response (null result)."
            )
            return None
        response = ReflectionSchema(**parsed)
        dumped = response.model_dump()
        return dumped
    except Exception as e:
        logger.error(f"[Parser] Error parsing reflection response: {e}", exc_info=True)
        return None
