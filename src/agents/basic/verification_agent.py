# src/agents/basic/verification_agent.py
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    get_buffer_string,
)

from src.agents.basic.base import BaseAgent
from src.agents.prompts.agent_prompts import PromptTemplates
from src.agents.tools.server.mcp_retrieve_tools import think
from src.core.config.llm_config import LLMModelConfigs
from src.core.config.settings import settings
from src.domain.entities.state import ThinkingState
from src.domain.schemas.graph import VerificationSchema
from src.utils import get_current_time, parse_response
from src.utils.decorators import singleton
from src.utils.logger_conf import logger


@singleton
class VerificationAgent(BaseAgent):
    """Agent responsible for verifying if we can answer the question well."""

    def __init__(self):
        super().__init__(
            provider="nxchat",
            config=LLMModelConfigs(
                model="nxchat-internal",
                base_url=settings.ntqai_base_url,
                api_key=settings.ntqai_api_key,
                temperature=0.0,
            ),
        )
        logger.info("Verification Agent initialized successfully.")

    async def ainvoke(self, state: ThinkingState) -> dict[str, Any]:
        """
        Verifies if we should continue researching or synthesize answer now.

        Returns:
            {
                "should_continue": bool,
                "missing_aspects": str,
            }
        """
        max_iterations = 3
        conversation_text = get_buffer_string(state["conversation"])
        internal_reasoning = state.get("_internal_reasoning", "").strip()
        accumulated_context = state.get("accumulated_context", "").strip()
        iteration_count = state.get("iteration_count", 0)
        consecutive_failures = state.get("consecutive_failures", 0)

        execution_history = state.get("execution_history", [])

        pattern_analysis = self._analyze_execution_pattern(execution_history)

        knowledge_summary = self._build_knowledge_summary(
            internal_reasoning=internal_reasoning,
            accumulated_context=accumulated_context,
            execution_history=execution_history,
            iteration_count=iteration_count,
            pattern_analysis=pattern_analysis,
            consecutive_failures=consecutive_failures,
        )

        messages: list[BaseMessage] = [
            SystemMessage(
                content=get_current_time() + PromptTemplates.VERIFICATION_PROMPT
            ),
            AIMessage(content=knowledge_summary),
            HumanMessage(
                content=f"<original_conversation>\n{conversation_text}\n</original_conversation>"
            ),
        ]

        verification_llm = self.thinking_llm
        verification_dict = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=verification_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_verification_response,
            retry_prompt='Return JSON: {"should_continue": true/false, "missing_aspects": "..."}',
        )

        return verification_dict

    def _analyze_execution_pattern(self, execution_history: list) -> dict[str, Any]:
        """
        Analyze recent execution pattern to detect stuck loops.

        Returns pattern info that verification agent needs to know.
        """
        if not execution_history or len(execution_history) < 2:
            return {
                "is_stuck": False,
                "pattern_type": "normal",
                "description": "Normal execution flow",
            }

        recent_5 = execution_history[-5:]

        # Check for repeated tool failures
        recent_failures = [ex for ex in recent_5 if ex.get("status") == "failed"]
        if len(recent_failures) >= 3:
            failed_tool = recent_failures[0].get("subgraph", "unknown")
            if all(ex.get("subgraph") == failed_tool for ex in recent_failures):
                return {
                    "is_stuck": True,
                    "pattern_type": "repeated_tool_failure",
                    "description": f"Tool '{failed_tool}' failed {len(recent_failures)} times in a row",
                    "failed_tool": failed_tool,
                    "last_error": recent_failures[-1].get("error", "Unknown"),
                }

        # Check for similar queries
        recent_queries = [ex.get("query", "")[:50].lower() for ex in recent_5]
        if len(recent_queries) >= 3:
            first_words = set(recent_queries[0].split())
            similar_count = sum(
                1
                for q in recent_queries[1:]
                if len(set(q.split()) & first_words) / max(len(set(q.split())), 1) > 0.6
            )
            if similar_count >= 2:
                return {
                    "is_stuck": True,
                    "pattern_type": "repeated_similar_queries",
                    "description": f"Last {similar_count + 1} queries are too similar, not finding new info",
                    "sample_queries": recent_queries[-3:],
                }

        if len(recent_5) >= 4:
            tools_used = [ex.get("subgraph", "") for ex in recent_5]
            unique_tools = set(tools_used)
            if len(unique_tools) == 2 and len(tools_used) >= 4:
                is_alternating = all(
                    tools_used[i] != tools_used[i + 1]
                    for i in range(len(tools_used) - 1)
                )
                if is_alternating:
                    return {
                        "is_stuck": True,
                        "pattern_type": "alternating_tools",
                        "description": f"Alternating between {', '.join(unique_tools)} without progress",
                        "tools": list(unique_tools),
                    }

        return {
            "is_stuck": False,
            "pattern_type": "normal",
            "description": "Normal execution flow",
        }

    def _build_knowledge_summary(
        self,
        internal_reasoning: str,
        accumulated_context: str,
        execution_history: list,
        iteration_count: int,
        pattern_analysis: dict,
        consecutive_failures: int,
    ) -> str:
        """
        Build summary with clear distinction between reasoning and external data.
        Shows LATEST content (last 400 chars) to reflect most recent progress.
        """
        summary_parts = []

        summary_parts.append(f"## Research Status: Iteration {iteration_count}")
        summary_parts.append("")

        if consecutive_failures > 0:
            summary_parts.append(f"⚠️ **Consecutive Failures**: {consecutive_failures}")
            summary_parts.append("")

        if pattern_analysis["is_stuck"]:
            summary_parts.append(
                f"🔴 **STUCK PATTERN DETECTED**: {pattern_analysis['description']}"
            )
            summary_parts.append(
                "   → Strong signal to stop and work with available information"
            )
            summary_parts.append("")

        has_reasoning = len(internal_reasoning) > 0
        has_external = len(accumulated_context) > 0

        summary_parts.append("### What We Have:")
        summary_parts.append("")

        if has_reasoning:
            reasoning_length = len(internal_reasoning)
            summary_parts.append(
                f"**Internal Reasoning**: {reasoning_length} chars of analysis/thinking"
            )
        else:
            summary_parts.append("**Internal Reasoning**: None yet")

        if has_external:
            external_length = len(accumulated_context)
            successful_searches = [
                ex for ex in execution_history if ex.get("status") == "success"
            ]
            summary_parts.append(
                f"**External Data**: {external_length} chars from {len(successful_searches)} successful tool calls"
            )
        else:
            summary_parts.append("**External Data**: None yet")

        summary_parts.append("")

        if execution_history:
            summary_parts.append("### Recent Attempts:")
            summary_parts.append("")

            recent_10 = execution_history[-3:]
            success_count = sum(1 for ex in recent_10 if ex.get("status") == "success")
            fail_count = len(recent_10) - success_count

            summary_parts.append(
                f"Last {len(recent_10)} iterations: {success_count} ✓ success, {fail_count} ✗ failed"
            )
            summary_parts.append("")

            for ex in recent_10[-3:]:
                iter_num = ex.get("iteration", "?")
                status = "✓" if ex.get("status") == "success" else "✗"
                subgraph = ex.get("subgraph", "unknown")
                query = ex.get("query", "")[:50]

                line = f'  [{iter_num}] {status} {subgraph}: "{query}"'

                if ex.get("status") == "success":
                    result_count = ex.get("result_count", "?")
                    line += f" → {result_count} results"
                else:
                    error = ex.get("error", "Unknown")[:60]
                    line += f" → {error}"

                summary_parts.append(line)
            summary_parts.append("")

        if has_reasoning:
            summary_parts.append("### Internal Reasoning (Latest):")
            summary_parts.append("")
            if len(internal_reasoning) > 8000:
                preview = "..." + internal_reasoning[-8000:]
            else:
                preview = internal_reasoning
            summary_parts.append(preview)
            summary_parts.append("")

        if has_external:
            summary_parts.append("### External Data (Latest):")
            summary_parts.append("")
            if len(accumulated_context) > 8000:
                preview = "..." + accumulated_context[-8000:]
            else:
                preview = accumulated_context
            summary_parts.append(preview)
            summary_parts.append("")

        summary_parts.append("### Note:")
        summary_parts.append(
            "- Internal Reasoning = analysis/thinking process (not concrete facts)"
        )
        summary_parts.append(
            "- External Data = specific facts/numbers/details from tools"
        )
        summary_parts.append(
            "- For factual questions: External Data required, reasoning alone insufficient"
        )

        return "\n".join(summary_parts)


def parse_verification_response(content: str) -> VerificationSchema | None:
    """Parse verification response"""
    try:
        parsed = parse_response(content)
        if not parsed:
            logger.warning(
                "[Parser] Failed to parse verification response (null result)."
            )
            return content
        response = VerificationSchema(**parsed)
        dumped = response.model_dump()
        return dumped
    except Exception as e:
        logger.error(
            f"[Parser] Error parsing verification response: {e}", exc_info=True
        )
        return content
