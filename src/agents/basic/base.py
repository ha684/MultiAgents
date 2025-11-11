# src/agents/basic/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import Tool
from src.agents.tools.server.mcp_retrieve_tools import think
from src.core.config.llm_config import SupportedLLMProviders
from src.llm.factory import get_llm
from src.utils.logger_conf import logger


class BaseAgent(ABC):
    """LLM utilities common to all agents (with or without graph)."""

    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        self.llm = get_llm(provider)
        self.thinking_llm = self.llm.bind_tools([think])

    async def simple_llm_call(
        self,
        messages: Iterable[BaseMessage],
        error_context: str = "Agent",
    ) -> AIMessage:
        try:
            prompt = ChatPromptTemplate.from_messages(list(messages))
            return await (prompt | self.llm.with_retry()).ainvoke({})
        except Exception as e:
            logger.error(f"{error_context}: Error in LLM call: {e}", exc_info=True)
            return AIMessage(content="")

    async def iterative_llm_call_text(
        self,
        messages: List[BaseMessage],
        llm_with_tools: BaseChatModel,
        available_tools: Dict[str, Tool],
        max_iterations: int,
        retry_prompt: str,
        fallback_value: str = "",
        error_context: str = "Agent",
        return_thinking: bool = False,
    ) -> Union[str, Tuple[str, Optional[str]]]:
        iteration = 0
        thinking_content = None

        while iteration < max_iterations:
            iteration += 1
            prompt = ChatPromptTemplate.from_messages(messages)
            response: AIMessage = await (prompt | llm_with_tools).ainvoke({})
            messages.append(response)

            if response.tool_calls:
                for tc in response.tool_calls:
                    if tc["name"] == "think":
                        thinking_content = tc["args"].get("thought", "")

            if response.content:
                if return_thinking:
                    return response.content, thinking_content
                return response

            if response.tool_calls:
                tool_outputs = []
                for tc in response.tool_calls:
                    tool = available_tools.get(tc["name"])
                    if tool:
                        tool_result = await tool.ainvoke(tc["args"])
                        tool_outputs.append(
                            ToolMessage(content=str(tool_result), tool_call_id=tc["id"])
                        )
                    else:
                        logger.warning(f"{error_context}: Unknown tool: {tc['name']}")
                messages.extend(tool_outputs)
            else:
                logger.warning(
                    f"{error_context}: No content/tool calls in iteration {iteration}"
                )
                if iteration < max_iterations:
                    messages.append(HumanMessage(content=retry_prompt))
                    continue
                break

        logger.error(
            f"{error_context}: Failed after {iteration} iterations. Returning fallback."
        )
        if return_thinking:
            return fallback_value, thinking_content
        return fallback_value

    async def iterative_llm_call_structured(
        self,
        messages: List[BaseMessage],
        llm_with_tools: BaseChatModel,
        available_tools: Dict[str, Tool],
        max_iterations: int,
        parse_fn: Callable[[str], Optional[Dict[str, Any]]],
        retry_prompt: str,
        error_context: str = "Agent",
    ) -> Optional[Dict[str, Any]]:
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            prompt = ChatPromptTemplate.from_messages(messages)
            response: AIMessage = await (prompt | llm_with_tools).ainvoke({})
            messages.append(response)

            if response.content:
                parsed = parse_fn(str(response.content))
                if parsed:
                    return parsed

            if not response.tool_calls:
                logger.warning(
                    f"{error_context}: No valid JSON and no tool calls at iter {iteration}. "
                    f"Response: {response.content[:200] if response.content else 'None'}"
                )
                if iteration < max_iterations:
                    messages.append(HumanMessage(content=retry_prompt))
                    continue
                break

            tool_outputs = []
            for tc in response.tool_calls:
                tool = available_tools.get(tc["name"])
                if tool:
                    tool_result = await tool.ainvoke(tc["args"])
                    tool_outputs.append(
                        ToolMessage(content=str(tool_result), tool_call_id=tc["id"])
                    )
                else:
                    logger.warning(f"{error_context}: Unknown tool: {tc['name']}")
            messages.extend(tool_outputs)

        logger.error(
            f"{error_context}: Structured call failed after {iteration} iterations."
        )
        return None

    @abstractmethod
    async def ainvoke(self, *args, **kwargs) -> Any: ...
