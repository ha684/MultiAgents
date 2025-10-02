from typing import List, Dict, Any, Callable, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import Tool
from langchain_core.prompts import ChatPromptTemplate
from src.utils.logger_conf import logger
from langchain_core.language_models.chat_models import BaseChatModel


class AgentBase:
    """Base class with common methods for agent patterns"""

    async def simple_llm_call(
        self,
        messages: List[BaseMessage],
        llm: BaseChatModel,
        error_context: str = "Agent",
    ) -> AIMessage:
        """
        Simple LLM call without tools - just get text response

        Args:
            messages: List of messages
            llm: LLM instance (not bind tools)
            error_context: Context string for logging

        Returns:
            Response content as string
        """
        try:
            prompt = ChatPromptTemplate.from_messages(messages)
            chain = prompt | llm
            response: AIMessage = await chain.ainvoke({})
            return response

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
    ) -> AIMessage:
        """
        Iterative LLM call with tools - returns text content

        Args:
            messages: List of messages
            llm_with_tools: LLM with tools bound
            available_tools: Dictionary of tools available
            max_iterations: Maximum number of retry attempts
            retry_prompt: Prompt to retry when no result
            fallback_value: Fallback value if failed
            error_context: Context string for logging

        Returns:
            Response content as string
        """
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            prompt = ChatPromptTemplate.from_messages(messages)
            chain = prompt | llm_with_tools
            response: AIMessage = await chain.ainvoke({})
            messages.append(response)

            if response.content:
                logger.info(f"{error_context}: Got response in iteration {iteration}")
                return response

            if response.tool_calls:
                tool_outputs = []
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    if tool_name in available_tools:
                        tool_to_call = available_tools[tool_name]
                        tool_result = await tool_to_call.ainvoke(tool_call["args"])
                        tool_outputs.append(
                            ToolMessage(
                                content=str(tool_result), tool_call_id=tool_call["id"]
                            )
                        )
                    else:
                        logger.warning(f"{error_context}: Unknown tool: {tool_name}")

                messages.extend(tool_outputs)
            else:
                logger.warning(
                    f"{error_context}: No content or tool calls in iteration {iteration}"
                )
                if iteration < max_iterations:
                    messages.append(HumanMessage(content=retry_prompt))
                    continue
                else:
                    break

        logger.error(
            f"{error_context}: Failed to get valid response after {iteration} iterations. "
            f"Returning fallback value."
        )
        return AIMessage(content=fallback_value)

    async def iterative_llm_call_structured(
        self,
        messages: List[BaseMessage],
        llm_with_tools: BaseChatModel,
        available_tools: Dict[str, Tool],
        max_iterations: int,
        parse_fn: Callable[[str], Optional[Dict[str, Any]]],
        retry_prompt: str,
        error_context: str = "Agent",
    ) -> Optional[AIMessage]:
        """
        Iterative LLM call with tools - returns parsed structured output

        Args:
            messages: List of messages
            llm_with_tools: LLM with tools bound
            available_tools: Dictionary of tools available
            max_iterations: Maximum number of retry attempts
            parse_fn: Function to parse response content
            retry_prompt: Prompt to retry when no result
            error_context: Context string for logging

        Returns:
            Parsed dictionary or None if failed
        """
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            prompt = ChatPromptTemplate.from_messages(messages)
            chain = prompt | llm_with_tools
            response: AIMessage = await chain.ainvoke({})
            messages.append(response)

            if response.content:
                parsed_result = parse_fn(str(response.content))
                if parsed_result:
                    logger.info(
                        f"{error_context}: Successfully parsed response in iteration {iteration}"
                    )
                    return AIMessage(content=parsed_result)

            if not response.tool_calls:
                logger.warning(
                    f"{error_context}: No valid JSON and no tool calls in iteration {iteration}. "
                    f"Response content: {response.content[:200] if response.content else 'None'}"
                )
                if iteration < max_iterations:
                    messages.append(HumanMessage(content=retry_prompt))
                    continue
                else:
                    break

            tool_outputs = []
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                if tool_name in available_tools:
                    tool_to_call = available_tools[tool_name]
                    tool_result = await tool_to_call.ainvoke(tool_call["args"])
                    tool_outputs.append(
                        ToolMessage(
                            content=str(tool_result), tool_call_id=tool_call["id"]
                        )
                    )
                else:
                    logger.warning(f"{error_context}: Unknown tool: {tool_name}")

            messages.extend(tool_outputs)

        logger.error(
            f"{error_context}: Failed to get valid response after {iteration} iterations."
        )
        return AIMessage(content="")
