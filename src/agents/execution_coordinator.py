from src.agents.com.registry import registry
from src.agents.graph.state import OrchestratorState
from typing import Dict, Any
from langchain_core.messages import HumanMessage
from src.utils import parse_response


class ExecutionCoordinator:
    """
    Điều phối việc chạy subgraphs theo plan.
    Đánh giá kết quả và quyết định next step.
    """

    def __init__(self, llm):
        self.llm = llm

    async def execute_step(self, state: OrchestratorState) -> Dict[str, Any]:
        """Execute current step in plan"""

        plan = state["execution_plan"]
        primary = plan["primary_strategy"]

        if primary == "direct_response":
            return {"execution_status": "completed", "next_action": "synthesize"}

        if primary not in state["attempted_subgraphs"]:
            result = await self._execute_subgraph(primary, state)

            evaluation = await self._evaluate_result(primary, result, state)

            updated_state = {
                "attempted_subgraphs": state["attempted_subgraphs"] + [primary],
                "subgraph_results": {**state["subgraph_results"], primary: result},
                "agent_thoughts": state["agent_thoughts"] + [evaluation["reasoning"]],
            }

            if evaluation["success"]:
                return {
                    **updated_state,
                    "execution_status": "completed",
                    "next_action": "synthesize",
                }
            else:
                return await self._handle_failure(plan, evaluation, updated_state)

        return {"execution_status": "completed"}

    async def _execute_subgraph(
        self, subgraph_name: str, state: OrchestratorState
    ) -> Dict[str, Any]:
        """Execute a specific subgraph"""
        config = registry.get_subgraph(subgraph_name)
        if not config:
            return {"error": f"Unknown subgraph: {subgraph_name}"}

        subgraph_state = {
            "contextualized_query": state["contextualized_query"],
            "conversation": state["conversation"],
        }

        try:
            result = await config.executor(subgraph_state)
            return result
        except Exception as e:
            return {"error": str(e)}

    async def _evaluate_result(
        self, subgraph_name: str, result: Dict, state: OrchestratorState
    ) -> Dict[str, Any]:
        """Evaluate if result is sufficient"""

        evaluation_prompt = f"""Evaluate this subgraph result:

Subgraph: {subgraph_name}
User query: {state["contextualized_query"]}
Result: {self._summarize_result(result)}

Does this result adequately answer the user's query?

Return JSON:
{{
    "success": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "explanation",
    "missing_info": "what's missing if not successful"
}}
"""

        response = await self.llm.ainvoke([HumanMessage(content=evaluation_prompt)])
        return parse_response(response.content)

    async def _handle_failure(
        self, plan: Dict, evaluation: Dict, state: Dict
    ) -> Dict[str, Any]:
        """Decide what to do when execution fails"""

        fallback_chain = plan.get("fallback_strategies", [])
        attempted = state["attempted_subgraphs"]

        next_fallback = None
        for fb in fallback_chain:
            if fb not in attempted:
                next_fallback = fb
                break

        if next_fallback:
            return {
                **state,
                "execution_plan": {**plan, "primary_strategy": next_fallback},
                "execution_status": "executing",
                "agent_thoughts": state["agent_thoughts"]
                + [f"Primary strategy insufficient. Trying fallback: {next_fallback}"],
            }
        else:
            return {
                **state,
                "execution_status": "awaiting_user",
                "next_action": "request_clarification",
                "agent_thoughts": state["agent_thoughts"]
                + ["All strategies exhausted. Need user guidance."],
            }

    def _summarize_result(self, result: Dict) -> str:
        """Summarize result for evaluation"""
        if "error" in result:
            return f"Error: {result['error']}"
        if "final_answer" in result:
            return f"Answer provided: {result['final_answer'][:200]}..."
        return str(result)[:300]
