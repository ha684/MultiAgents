# src/agents/basic/router_agent.py
from typing import Any, Dict, List, Optional, Tuple, Union

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.agents.prompts.agent_prompts import PromptTemplates
from src.agents.tools.server.mcp_retrieve_tools import think
from src.core.config.llm_config import SupportedLLMProviders
from src.domain.entities.state import OrchestratorState, ReflectionResult, ResearchState
from src.utils import parse_response
from src.utils.logger_conf import logger


class ReflectionAgent(BaseAgent):
    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        super().__init__(provider)

    async def ainvoke(
        self, state: OrchestratorState | ResearchState
    ) -> Union[ReflectionResult, Tuple[str, Optional[str]]]:
        if "subgraph_results" in state:  # OrchestratorState
            current_iteration = state.get("current_iteration", 1)
            max_iterations = state.get("max_iterations")
            search_iterations = state.get("search_iterations", [])
            subgraph_results = state.get("subgraph_results", {})
            failed_subgraphs = state.get("failed_subgraphs", set())

            subgraph_summary = []
            successful_subgraphs = []
            failed_subgraph_list = []
            empty_subgraphs = []

            for subgraph_name, result_data in subgraph_results.items():
                status = result_data.get("status", "unknown")
                error = result_data.get("error")
                iteration = result_data.get("iteration", 0)
                main_context = result_data.get("main_context", "")

                summary_line = f"  • {subgraph_name} (iteration {iteration}): "

                if status == "success":
                    successful_subgraphs.append(subgraph_name)
                    summary_line += f"✓ SUCCESS - Context: {main_context}"
                elif status == "error":
                    failed_subgraph_list.append(subgraph_name)
                    summary_line += (
                        f"✗ ERROR - {error}\n    (This subgraph will NOT be retried)"
                    )
                elif status == "empty":
                    empty_subgraphs.append(subgraph_name)
                    summary_line += (
                        "○ EMPTY - Executed successfully but found no results"
                    )
                else:
                    summary_line += "? UNKNOWN STATUS"

                subgraph_summary.append(summary_line)

            subgraph_summary_text = (
                "\n".join(subgraph_summary)
                if subgraph_summary
                else "No subgraphs executed yet"
            )

            search_history_lines = []
            for it in search_iterations:
                status_icon = (
                    "✓"
                    if it.get("status") == "success"
                    else "✗"
                    if it.get("status") == "error"
                    else "○"
                )
                search_history_lines.append(
                    f"  {status_icon} Iteration {it['iteration']}: {it['subgraph']} ({it.get('status', 'unknown')})"
                )
            search_history_text = (
                "\n".join(search_history_lines)
                if search_history_lines
                else "No previous searches"
            )

            available_for_retry = [
                sg
                for sg in successful_subgraphs + empty_subgraphs
                if sg not in failed_subgraphs
            ]

            system_prompt = SystemMessage(
                content=PromptTemplates.ORCHESTRATOR_REFLECTION_PROMPT
            )

            human_prompt = HumanMessage(
                content=PromptTemplates.ORCHESTRATOR_REFLECTION_HUMAN_PROMPT.format(
                    user_query=state["conversation"][-1].content,
                    current_iteration=current_iteration,
                    max_iterations=max_iterations,
                    search_history=search_history_text,
                    subgraph_results=subgraph_summary_text,
                    successful_subgraphs=", ".join(successful_subgraphs)
                    if successful_subgraphs
                    else "None",
                    failed_subgraphs=", ".join(failed_subgraph_list)
                    if failed_subgraph_list
                    else "None",
                    empty_subgraphs=", ".join(empty_subgraphs)
                    if empty_subgraphs
                    else "None",
                    available_for_retry=", ".join(available_for_retry)
                    if available_for_retry
                    else "None",
                )
            )
            messages: List[BaseMessage] = [system_prompt, human_prompt]
            reflection_result = await self.iterative_llm_call_structured(
                messages=messages,
                llm_with_tools=self.thinking_llm,
                available_tools={"think": think},
                max_iterations=3,
                parse_fn=parse_reflection_result,
                retry_prompt=(
                    "Please provide the reflection result in correct JSON format with all required fields including 'subgraphs_to_retry'."
                ),
            )
            return reflection_result

        else:
            learnings = state.get("learnings", [])
            knowledge = state.get("accumulated_knowledge", "")

            prompt_input = PromptTemplates.REFLECTION_HUMAN_PROMPT.format(
                original_query=state["contextualized_query"],
                learnings="\n".join(f"- {learning}" for learning in learnings[-3:])
                if learnings
                else "None yet",
                knowledge=knowledge[-3000:] if knowledge else "None yet",
            )

            messages: List[BaseMessage] = [
                SystemMessage(content=PromptTemplates.REFLECTION_PROMPT),
                HumanMessage(content=prompt_input),
            ]

            reflection_result, thinking_content = await self.iterative_llm_call_text(
                messages=messages,
                llm_with_tools=self.thinking_llm,
                available_tools={"think": think},
                max_iterations=3,
                retry_prompt="Please provide the reflection in the correct JSON format.",
                return_thinking=True,
            )
            return reflection_result, thinking_content


def parse_reflection_result(content: str) -> Optional[Dict[str, Any]]:
    """Parse reflection result from content"""
    try:
        parsed = parse_response(content)
        if parsed is None:
            return None
        return parsed
    except Exception as e:
        logger.error(f"Error parsing reflection result: {e}")
        return None
