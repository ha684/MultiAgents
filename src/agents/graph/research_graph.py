# src/agents/graph/research_graph.py
import json
from datetime import datetime
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from src.agents.basic import citation_agent, summary_agent
from src.agents.tools.server.mcp_retrieve_tools import rag_search, web_search, think
from src.utils.logger_conf import logger
from src.agents.graph.state import AgentState, SearchResult
from src.agents.graph.prompts import PromptTemplates
from src.agents.graph.schemas import (
    SearchPlanSchema,
    VerificationSchema,
    DynamicQueriesSchema,
)
from src.llm.factory import get_llm


class ResearchGraph:
    """Research Subgraph - Deep research with iterative search loop"""

    def __init__(self):
        self.llm = get_llm("nxchat")
        self.tools = [think]
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        self.graph = self._build_graph()

    # =========================================================================
    # NODE IMPLEMENTATIONS
    # =========================================================================

    async def query_planner_node(self, state: AgentState) -> Dict[str, Any]:
        """Create research plan - LLM tự suy luận với think và output JSON"""
        logger.info("Research - Query Planner")

        # Prompt hướng dẫn LLM dùng think tool và output JSON
        prompt = f"""
{PromptTemplates.QUERY_PLANNER_PROMPT.format(original_query=state["contextualized_query"])}

You can use the 'think' tool to reason step-by-step before creating the plan.
After reasoning, provide your final search plan in this JSON format:

{json.dumps(SearchPlanSchema.model_json_schema(), indent=2)}

Make sure to output valid JSON that matches the schema above.
"""

        response = await self.llm_with_tools.ainvoke(prompt)

        # Parse JSON từ response content
        try:
            # LLM có thể wrap JSON trong ```json hoặc trả thẳng
            content = response.content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()

            plan_dict = json.loads(json_str)
            plan = SearchPlanSchema(**plan_dict)
            plan_dict = plan.model_dump()

        except Exception as e:
            logger.error(f"Failed to parse plan: {e}")
            plan_dict = {
                "core_queries": [
                    {
                        "query": state["contextualized_query"],
                        "search_type": "rag",
                        "priority": 1,
                    }
                ],
                "optional_queries": [],
                "max_searches": 3,
            }

        all_queries = plan_dict["core_queries"] + plan_dict["optional_queries"]
        all_queries.sort(key=lambda x: x.get("priority", 0))

        logger.info(
            f"Plan: {len(plan_dict['core_queries'])} core, "
            f"{len(plan_dict['optional_queries'])} optional queries"
        )

        return {
            "search_plan": plan_dict,
            "pending_queries": all_queries,
            "max_searches": plan_dict["max_searches"],
            "iteration_count": 0,
            "accumulated_knowledge": "",
            "all_search_history": [],
            "used_rag_ids": [],
            "used_web_urls": [],
            "should_switch_search_type": False,
        }

    async def search_executor_node(
        self, state: AgentState, tool_context: Any
    ) -> Dict[str, Any]:
        """Execute search query"""
        if not state["pending_queries"]:
            return {}

        current_query = state["pending_queries"][0]
        search_type = current_query["search_type"]
        query_text = current_query["query"]

        logger.info(f"Research - Search: {search_type} - '{query_text}'")

        try:
            if search_type == "rag":
                content, source_ids = await rag_search(
                    query=query_text, top_k=20, top_n=5, tool_context=tool_context
                )
            else:
                content, source_ids = await web_search(
                    query=query_text, top_k=20, top_n=5, tool_context=tool_context
                )
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return {
                "completed_queries": state["completed_queries"] + [current_query],
                "pending_queries": state["pending_queries"][1:],
                "iteration_count": state["iteration_count"] + 1,
            }

        search_result = SearchResult(
            query=query_text,
            content=content,
            source_ids=source_ids,
            search_type=search_type,
            timestamp=datetime.now().isoformat(),
        )

        logger.info(f"Retrieved {len(source_ids)} sources")

        return {
            "search_results": [search_result],
            "completed_queries": state["completed_queries"] + [current_query],
            "pending_queries": state["pending_queries"][1:],
            "all_search_history": state["all_search_history"] + [search_result],
            "iteration_count": state["iteration_count"] + 1,
        }

    async def process_results_node(self, state: AgentState) -> Dict[str, Any]:
        """Filter, compress, merge results"""
        if not state["search_results"]:
            return {}

        latest = state["search_results"][0]
        source_ids = latest["source_ids"]
        search_type = latest["search_type"]

        logger.info(f"Research - Processing {len(source_ids)} {search_type} sources")

        # Check redundancy
        if search_type == "rag":
            overlap = set(source_ids) & set(state["used_rag_ids"])
            ratio = len(overlap) / max(len(source_ids), 1)
            if ratio > 0.7:
                logger.warning(f"RAG overlap {ratio:.1%} - switch to web")
                return {"should_switch_search_type": True}
        else:
            overlap = set(source_ids) & set(state["used_web_urls"])
            ratio = len(overlap) / max(len(source_ids), 1)
            if ratio > 0.7:
                logger.warning(f"Web overlap {ratio:.1%} - switch to RAG")
                return {"should_switch_search_type": True}

        # Filter with citation agent
        relevant_indices = await citation_agent.extract_citations(
            query=latest["query"], documents=latest["content"]
        )

        if not relevant_indices:
            logger.warning("No relevant documents")
            return {}

        # Compress
        compressed = await summary_agent.compress_content(
            content=latest["content"],
            relevant_indices=relevant_indices,
            query=latest["query"],
        )

        # Merge
        if state["accumulated_knowledge"]:
            merged = (
                f"{state['accumulated_knowledge']}\n\n"
                f"--- {latest['query']} ---\n\n{compressed}"
            )
        else:
            merged = compressed

        # Update tracking
        new_rag = state["used_rag_ids"]
        new_web = state["used_web_urls"]

        if search_type == "rag":
            new_rag = list(set(state["used_rag_ids"] + source_ids))
        else:
            new_web = list(set(state["used_web_urls"] + source_ids))

        logger.info(f"Knowledge updated (RAG: {len(new_rag)}, Web: {len(new_web)})")

        return {
            "accumulated_knowledge": merged,
            "used_rag_ids": new_rag,
            "used_web_urls": new_web,
            "should_switch_search_type": False,
        }

    async def verification_agent_node(self, state: AgentState) -> Dict[str, Any]:
        """Verify sufficiency - dùng think và output JSON"""
        logger.info(
            f"Research - Verification ({state['iteration_count']}/{state['max_searches']})"
        )

        prompt = f"""
{
            PromptTemplates.VERIFICATION_PROMPT.format(
                original_query=state["contextualized_query"],
                accumulated_knowledge=state["accumulated_knowledge"],
                pending_queries=json.dumps(
                    [q["query"] for q in state["pending_queries"]]
                ),
                iteration_count=state["iteration_count"],
                max_searches=state["max_searches"],
            )
        }

Use the 'think' tool to analyze step-by-step, then output your decision in this JSON format:

{json.dumps(VerificationSchema.model_json_schema(), indent=2)}
"""

        response = await self.llm_with_tools.ainvoke(prompt)

        try:
            content = response.content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()

            verification_dict = json.loads(json_str)
            verification = VerificationSchema(**verification_dict)
            verification_dict = verification.model_dump()

        except Exception as e:
            logger.error(f"Failed to parse verification: {e}")
            # Fallback
            verification_dict = {
                "next_action": "synthesize",
                "confidence": 0.5,
                "missing_aspects": [],
            }

        logger.info(
            f"Decision: {verification_dict['next_action']} "
            f"(confidence: {verification_dict['confidence']:.2f})"
        )

        return {"verification_result": verification_dict}

    async def dynamic_query_generator_node(self, state: AgentState) -> Dict[str, Any]:
        """Generate dynamic queries"""
        logger.info("Research - Dynamic Query Generation")

        verification = state["verification_result"]
        if not verification or not verification["missing_aspects"]:
            return {}

        prompt = f"""
{
            PromptTemplates.DYNAMIC_QUERY_GENERATOR_PROMPT.format(
                original_query=state["contextualized_query"],
                accumulated_knowledge=state["accumulated_knowledge"],
                missing_aspects=json.dumps(verification["missing_aspects"]),
            )
        }

Use 'think' tool to reason, then output queries in this JSON format:

{json.dumps(DynamicQueriesSchema.model_json_schema(), indent=2)}
"""

        response = await self.llm_with_tools.ainvoke(prompt)

        try:
            content = response.content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()

            result_dict = json.loads(json_str)
            result = DynamicQueriesSchema(**result_dict)
            new_queries = result.queries

        except Exception as e:
            logger.error(f"Failed to parse queries: {e}")
            new_queries = []

        logger.info(f"Generated {len(new_queries)} dynamic queries")

        return {"pending_queries": state["pending_queries"] + new_queries}

    # =========================================================================
    # ROUTING
    # =========================================================================

    def route_after_verification(self, state: AgentState) -> str:
        """Route based on verification"""
        if state["iteration_count"] >= state["max_searches"]:
            logger.info("Route: Max iterations → END")
            return "__end__"

        verification = state["verification_result"]
        if not verification:
            return "__end__"

        action = verification["next_action"]

        # Handle search type switching
        if state.get("should_switch_search_type"):
            recent = state["completed_queries"][-2:]
            recent_types = [q["search_type"] for q in recent]

            if all(t == "rag" for t in recent_types):
                logger.info("Route: Switch to web")
                if state["pending_queries"]:
                    state["pending_queries"][0]["search_type"] = "web"
                    return "search_executor"
                return "dynamic_query_generator"

            elif all(t == "web" for t in recent_types):
                logger.info("Route: Both exhausted → END")
                return "__end__"

        # Normal routing
        if action == "synthesize":
            return "__end__"
        elif action == "continue_planned":
            if not state["pending_queries"]:
                return "dynamic_query_generator"
            return "search_executor"
        elif action == "generate_dynamic":
            return "dynamic_query_generator"

        return "__end__"

    # =========================================================================
    # GRAPH CONSTRUCTION
    # =========================================================================

    def _build_graph(self) -> CompiledStateGraph:
        """Build research graph - KHÔNG CẦN ToolNode trong graph"""
        workflow = StateGraph(AgentState)

        # Chỉ cần các node chính
        workflow.add_node("query_planner", self.query_planner_node)
        workflow.add_node("search_executor", self.search_executor_node)
        workflow.add_node("process_results", self.process_results_node)
        workflow.add_node("verification_agent", self.verification_agent_node)
        workflow.add_node("dynamic_query_generator", self.dynamic_query_generator_node)

        workflow.set_entry_point("query_planner")

        # Edges đơn giản
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

    async def run(self, state: AgentState, tool_context: Any) -> AgentState:
        """Run research graph"""
        result = await self.graph.ainvoke(state, {"tool_context": tool_context})
        return result
