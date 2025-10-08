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
)
from src.llm.factory import get_llm
from src.agents.basic.base import AgentBase
from src.utils import parse_response


class ResearchGraph(AgentBase):
    """Research Subgraph - Deep research with iterative search loop"""

    def __init__(self):
        logger.info("Initializing ResearchGraph...")
        self.llm = get_llm("nxchat")
        self.thinking_llm = self.llm.bind_tools([think])
        self.graph = self._build_graph()
        logger.info("ResearchGraph initialized successfully.")

    async def query_planner_node(self, state: ResearchState) -> Dict[str, Any]:
        """Create research plan"""
        logger.info("[QueryPlanner] Starting...")
        logger.info(
            f"[QueryPlanner] Generating plan for query: '{state['contextualized_query']}'"
        )

        max_iterations = 3
        max_searches_range = "2-10"

        system_prompt = SystemMessage(
            content=PromptTemplates.QUERY_PLANNER_PROMPT.format(
                max_searches_range=max_searches_range
            )
        )
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

        if not response:
            logger.error("[QueryPlanner] Failed to generate a valid search plan.")
            return {"pending_queries": []}

        all_queries: List[SearchQuery] = response["queries"]
        all_queries.sort(key=lambda x: x.get("priority", 0), reverse=True)

        logger.info(
            f"[QueryPlanner] Plan generated: {len(response['queries'])} queries. Max searches: {response['max_searches']}"
        )
        logger.debug(f"[QueryPlanner] Full plan: {json.dumps(response, indent=2)}")

        return {
            "search_plan": response,
            "pending_queries": all_queries,
            "completed_queries": [],
            "max_searches": response["max_searches"],
            "iteration_count": 0,
            "accumulated_knowledge": "",
            "all_search_history": [],
            "used_rag_ids": [],
            "used_web_urls": [],
            "should_switch_search_type": False,
            "has_tried_rag": False,
            "has_tried_web": False,
        }

    async def search_executor_node(self, state: ResearchState) -> Dict[str, Any]:
        """Execute search query"""
        logger.info("[SearchExecutor] Starting...")
        if not state["pending_queries"]:
            logger.warning("[SearchExecutor] No pending queries. Skipping execution.")
            return {}

        current_query = state["pending_queries"][0]
        search_type = current_query["search_type"]
        query_text = current_query["query"]
        context_metadata = state["context_metadata"]
        has_tried_rag = state.get("has_tried_rag", False)
        has_tried_web = state.get("has_tried_web", False)
        logger.info(
            f"[SearchExecutor] Executing search ({search_type.upper()}) for query: '{query_text}'"
        )

        try:
            if search_type == "rag":
                documents = await rag_search(
                    query=query_text, context_metadata=context_metadata
                )
                has_tried_rag = True
            else:
                documents = await web_search(
                    query=query_text,
                )
                has_tried_web = True
        except Exception as e:
            logger.error(
                f"[SearchExecutor] Search failed for '{query_text}': {e}", exc_info=True
            )
            return {
                "completed_queries": state["completed_queries"] + [current_query],
                "pending_queries": state["pending_queries"][1:],
                "iteration_count": state["iteration_count"] + 1,
                "has_tried_rag": has_tried_rag,
                "has_tried_web": has_tried_web,
            }

        search_result = SearchResult(
            query=query_text, documents=documents, search_type=search_type
        )

        return {
            "search_results": search_result,
            "completed_queries": state["completed_queries"] + [current_query],
            "pending_queries": state["pending_queries"][1:],
            "all_search_history": state["all_search_history"] + [search_result],
            "iteration_count": state["iteration_count"] + 1,
            "has_tried_rag": has_tried_rag,
            "has_tried_web": has_tried_web,
        }

    async def process_results_node(self, state: ResearchState) -> Dict[str, Any]:
        """Filter, compress, merge results with hybrid strategy"""
        logger.info("[ProcessResults] Starting...")
        if not state["search_results"] or not state["search_results"]["documents"]:
            logger.warning("[ProcessResults] No search results to process. Skipping.")
            return {}

        overlap_threshold = 0.7
        consolidation_threshold = 4000
        consolidation_interval = 3

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
            logger.info(
                f"[ProcessResults] Web source overlap check: {len(overlap)}/{len(source_ids)} ({ratio:.1%})"
            )
            if ratio > overlap_threshold:
                logger.warning(
                    f"[ProcessResults] High web source overlap ({ratio:.1%}). Switching to RAG."
                )
                return {"should_switch_search_type": True}
        else:
            source_ids = [doc.metadata.get("document_id", "") for doc in documents]
            new_documents = [
                doc
                for doc in documents
                if doc.metadata.get("document_id", "") not in state["used_rag_ids"]
            ]
            overlap = set(source_ids) & set(state["used_rag_ids"])
            ratio = len(overlap) / max(len(source_ids), 1)
            logger.info(
                f"[ProcessResults] RAG source overlap check: {len(overlap)}/{len(source_ids)} ({ratio:.1%})"
            )
            if ratio > overlap_threshold:
                logger.warning(
                    f"[ProcessResults] High RAG source overlap ({ratio:.1%}). Switching to Web."
                )
                return {"should_switch_search_type": True}

        if not new_documents:
            logger.warning(
                "[ProcessResults] All documents already used. Switching search type."
            )
            return {"should_switch_search_type": True}

        logger.info(
            f"[ProcessResults] Filtering {len(new_documents)} new documents (from {len(documents)} total)."
        )
        relevant_indices = await citation_agent.ainvoke(
            history=[HumanMessage(content=current_query)], reference=new_documents
        )

        if not relevant_indices or not relevant_indices.indexes:
            logger.warning(
                "[ProcessResults] Citation agent found no relevant documents."
            )
            return {}

        cited_docs = [
            new_documents[i - 1]
            for i in relevant_indices.indexes
            if 0 < i <= len(new_documents)
        ]
        logger.info(f"[ProcessResults] Found {len(cited_docs)} relevant documents.")

        accumulated_len = len(state["accumulated_knowledge"])
        iteration = state["iteration_count"]

        should_consolidate = (
            ratio > overlap_threshold * 0.8
            or iteration > 0
            and iteration % consolidation_interval == 0
            or accumulated_len > consolidation_threshold
        )
        logger.info(
            f"[ProcessResults] Consolidation check: {should_consolidate} (ratio: {ratio:.1%}, iter: {iteration}, len: {accumulated_len})"
        )

        if should_consolidate and state["accumulated_knowledge"]:
            logger.info(
                "[ProcessResults] Consolidating new docs with existing knowledge."
            )
            new_merged = await compress_agent.ainvoke_with_merge(
                query=current_query,
                new_documents=cited_docs,
                existing_knowledge=state["accumulated_knowledge"],
            )
            merged = new_merged if new_merged else state["accumulated_knowledge"]
        else:
            logger.info("[ProcessResults] Compressing new documents.")
            compressed = await compress_agent.ainvoke(
                query=current_query, reference=cited_docs
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

        logger.info(
            f"[ProcessResults] Knowledge updated from {accumulated_len} to {len(merged)} chars. "
            f"Total sources used (RAG: {len(new_rag_ids)}, Web: {len(new_web_urls)})"
        )
        logger.info(f"[ProcessResults] Accumulated knowledge : {merged}")
        return {
            "accumulated_knowledge": merged,
            "used_rag_ids": new_rag_ids,
            "used_web_urls": new_web_urls,
            "should_switch_search_type": False,
        }

    async def verification_agent_node(self, state: ResearchState) -> Dict[str, Any]:
        """Verify sufficiency"""
        logger.info(
            f"[Verification] Starting... (Iteration {state['iteration_count']}/{state['max_searches']})"
        )

        max_iterations = 3
        prompt_input = PromptTemplates.VERIFICATION_HUMAN_PROMPT.format(
            original_query=state["contextualized_query"],
            accumulated_knowledge=state["accumulated_knowledge"],
            pending_queries=json.dumps([q["query"] for q in state["pending_queries"]]),
            iteration_count=state["iteration_count"],
            remaining_iterations=state["max_searches"] - state["iteration_count"],
            max_searches=state["max_searches"],
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
                "[Verification] Failed to get a valid verification. Defaulting to 'synthesize'."
            )
            return {"verification_result": {"next_action": "synthesize"}}

        logger.info(f"[Verification] Decision: '{verification_dict['next_action']}'")

        return {"verification_result": verification_dict}

    async def dynamic_query_generator_node(
        self, state: ResearchState
    ) -> Dict[str, Any]:
        """Generate dynamic queries"""
        logger.info("[DynamicQueryGenerator] Starting...")

        max_iterations = 3
        verification = state["verification_result"]
        if not verification or not verification.get("missing_aspects"):
            logger.warning(
                "[DynamicQueryGenerator] No missing aspects identified. Skipping query generation."
            )
            return {}

        logger.info(
            f"[DynamicQueryGenerator] Generating queries for missing aspects: {verification['missing_aspects']}"
        )
        prompt_input = PromptTemplates.DYNAMIC_QUERY_GENERATOR_HUMAN_PROMPT.format(
            original_query=state["contextualized_query"],
            accumulated_knowledge=state["accumulated_knowledge"],
            missing_aspects=json.dumps(verification["missing_aspects"]),
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
            return {}

        new_queries = dynamic_query_generator_dict.get("queries", [])
        logger.info(
            f"[DynamicQueryGenerator] Generated {len(new_queries)} new queries."
        )
        logger.debug(
            f"[DynamicQueryGenerator] New queries: {[q['query'] for q in new_queries]}"
        )

        return {"pending_queries": state["pending_queries"] + new_queries}

    def route_after_verification(self, state: ResearchState) -> str:
        """Route based on verification"""
        iteration = state["iteration_count"]
        max_searches = state["max_searches"]
        logger.info(
            f"[Router] Evaluating route after iteration {iteration}/{max_searches}"
        )

        if iteration >= max_searches:
            logger.info(f"[Router] Route: Max iterations ({iteration}) reached → END")
            return "__end__"

        verification = state["verification_result"]
        if not verification:
            logger.warning("[Router] Route: No verification result found → END")
            return "__end__"

        action = verification["next_action"]

        if state.get("should_switch_search_type"):
            logger.info(
                "[Router] 'should_switch_search_type' is True. Attempting to switch."
            )
            last_search_type = (
                state["completed_queries"][-1]["search_type"]
                if state["completed_queries"]
                else "rag"
            )
            has_tried_rag = state.get("has_tried_rag", False)
            has_tried_web = state.get("has_tried_web", False)

            if last_search_type == "rag" and not has_tried_web:
                logger.info(
                    "[Router] Route: High RAG overlap, switching to Web search."
                )
                target_search_type = "web"
            elif last_search_type == "web" and not has_tried_rag:
                logger.info(
                    "[Router] Route: High Web overlap, switching to RAG search."
                )
                target_search_type = "rag"
            else:
                logger.warning(
                    f"[Router] Route: High overlap detected. "
                    f"Already tried: RAG={has_tried_rag}, Web={has_tried_web}. "
                    f"Both sources may be exhausted → END"
                )
                return "__end__"

            if state["pending_queries"]:
                state["pending_queries"][0]["search_type"] = target_search_type
                logger.info(
                    f"[Router] Next query '{state['pending_queries'][0]['query']}' set to '{target_search_type}'."
                )
                return "search_executor"
            else:
                logger.info(
                    f"[Router] No pending queries. Generating dynamic queries for {target_search_type} search."
                )
                return "dynamic_query_generator"

        if action == "synthesize":
            logger.info("[Router] Route: Verification agent chose 'synthesize' → END")
            return "__end__"
        elif action == "continue_planned":
            if not state["pending_queries"]:
                logger.info(
                    "[Router] Route: 'continue_planned' but no pending queries. Switching to dynamic generation."
                )
                return "dynamic_query_generator"
            logger.info(
                "[Router] Route: 'continue_planned' with pending queries → search_executor"
            )
            return "search_executor"
        elif action == "generate_dynamic":
            logger.info("[Router] Route: 'generate_dynamic' → dynamic_query_generator")
            return "dynamic_query_generator"

        logger.warning(f"[Router] Route: Unknown action '{action}' → END")
        return "__end__"

    def _build_graph(self) -> CompiledStateGraph:
        """Build research graph"""
        workflow = StateGraph(ResearchState)

        workflow.add_node("query_planner", self.query_planner_node)
        workflow.add_node("search_executor", self.search_executor_node)
        workflow.add_node("process_results", self.process_results_node)
        workflow.add_node("verification_agent", self.verification_agent_node)
        workflow.add_node("dynamic_query_generator", self.dynamic_query_generator_node)

        workflow.set_entry_point("query_planner")

        workflow.add_edge("query_planner", "search_executor")
        workflow.add_edge("search_executor", "process_results")
        workflow.add_edge("process_results", "verification_agent")
        workflow.add_edge("dynamic_query_generator", "search_executor")

        workflow.add_conditional_edges(
            "verification_agent",
            self.route_after_verification,
            {
                "search_executor": "search_executor",
                "dynamic_query_generator": "dynamic_query_generator",
                "__end__": END,
            },
        )

        return workflow.compile()

    async def run(self, state: ResearchState) -> ResearchState:
        """Run research graph"""
        logger.info(
            f"--- Running ResearchGraph for query: '{state.get('contextualized_query')}' ---"
        )
        config = {"recursion_limit": 50}
        result = await self.graph.ainvoke(state, config=config)
        logger.info(
            f"--- ResearchGraph finished. Final knowledge length: {len(result.get('accumulated_knowledge', ''))} chars. ---"
        )
        return result


def parse_planner_response(content: str) -> Optional[SearchPlanSchema]:
    """Parse planner response"""
    logger.debug(f"[Parser] Parsing Planner response: {content}")
    try:
        parsed = parse_response(content)
        if parsed is None:
            logger.warning("[Parser] Failed to parse planner response (null result).")
            return None
        response = SearchPlanSchema(**parsed)
        dumped = response.model_dump()
        logger.info("[Parser] Successfully parsed planner response.")
        return dumped
    except Exception as e:
        logger.error(f"[Parser] Error parsing planner response: {e}", exc_info=True)
        return None


def parse_verification_response(content: str) -> Optional[VerificationSchema]:
    """Parse verification response"""
    logger.debug(f"[Parser] Parsing Verification response: {content}")
    try:
        parsed = parse_response(content)
        if parsed is None:
            logger.warning(
                "[Parser] Failed to parse verification response (null result)."
            )
            return None
        response = VerificationSchema(**parsed)
        dumped = response.model_dump()
        logger.info("[Parser] Successfully parsed verification response.")
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
    logger.debug(f"[Parser] Parsing Dynamic Query Generator response: {content}")
    try:
        parsed = parse_response(content)
        if parsed is None:
            logger.warning(
                "[Parser] Failed to parse dynamic query generator response (null result)."
            )
            return None
        response = DynamicQueriesSchema(**parsed)
        dumped = response.model_dump()
        logger.info("[Parser] Successfully parsed dynamic query generator response.")
        return dumped
    except Exception as e:
        logger.error(
            f"[Parser] Error parsing dynamic query generator response: {e}",
            exc_info=True,
        )
        return None
