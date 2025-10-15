from src.agents.main_graph import OrchestratorGraph
from src.models.chat import SearchProvider, WebSearchConfig
from langchain_core.messages import HumanMessage
from src.config.settings import settings
from src.utils.logger_conf import logger
from langchain_core.runnables.schema import StreamEvent
import asyncio
import time


class OrchestratorStreamer:
    """Helper class to visualize streaming from OrchestratorGraph"""

    def __init__(self):
        self.colors = {
            "blue": "\033[94m",
            "green": "\033[92m",
            "yellow": "\033[93m",
            "red": "\033[91m",
            "cyan": "\033[96m",
            "magenta": "\033[95m",
            "reset": "\033[0m",
        }

    def _print_box(self, title: str, content: str = "", color: str = "blue"):
        """Print colored box"""
        c = self.colors.get(color, self.colors["blue"])
        reset = self.colors["reset"]
        print(f"\n{c}{'=' * 70}{reset}")
        print(f"{c}║ {title}{reset}")
        if content:
            print(f"{c}║{reset} {content}")
        print(f"{c}{'=' * 70}{reset}")

    async def stream_orchestrator(
        self, orchestrator: OrchestratorGraph, conversation: list
    ):
        """Stream orchestrator execution with visual feedback"""

        self._print_box("🚀 STARTING ORCHESTRATOR", color="cyan")
        print(f"📝 Query: {conversation[-1].content}\n")

        llm_buffer = ""
        final_result = None

        is_graph_completed = False

        stats = {"nodes": [], "tokens": 0, "tools": 0, "start_time": time.time()}

        async for event in orchestrator.stream(conversation):
            event: StreamEvent
            kind = event["event"]
            name = event.get("name", "")

            if kind == "on_chain_start":
                stats["nodes"].append(name)
                if name in ["SimpleSearchGraph", "ResearchGraph", "MainOrchestrator"]:
                    self._print_box(f"🔄 Graph: {name}", color="blue")
                else:
                    self._print_box(f"🔄 NODE: {name}", color="blue")

            elif kind == "on_chain_end":
                output = event.get("data", {}).get("output")

                if name == "MainOrchestrator" and not is_graph_completed:
                    is_graph_completed = True
                    final_result = output
                    continue

                if name in ["SimpleSearchGraph", "ResearchGraph"]:
                    self._print_box(f"✅ Graph: {name} COMPLETED", color="green")
                    continue

                if output and name not in [
                    "RunnableSequence",
                    "RunnableLambda",
                    "route_after_router",
                ]:
                    self._print_box(
                        f"✅ NODE: {name}", content=str(output), color="green"
                    )

            elif kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    print(chunk.content, end="", flush=True)
                    llm_buffer += chunk.content
                    stats["tokens"] += len(chunk.content) // 4
                if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                    for tc in chunk.tool_call_chunks:
                        tool_name = tc.get("name")
                        if tool_name:
                            print(f"\n🔧 [Tool: {tool_name}]", flush=True)
                            stats["tools"] += 1
                        args = tc.get("args")
                        if args:
                            stats["tokens"] += len(args) // 4
                            print(args, end="", flush=True)
            elif kind == "on_chat_model_end":
                if llm_buffer:
                    print("\n")
                    llm_buffer = ""

        self._print_box("✅ Orchestrator Graph COMPLETED", color="green")

        duration = time.time() - stats["start_time"]
        self._print_box(
            "📊 EXECUTION SUMMARY",
            f"Time: {duration:.2f}s | Nodes: {len(stats['nodes'])} | "
            f"Tokens: {stats['tokens']} | Tools: {stats['tools']}",
            color="magenta",
        )
        print(f"\n📍 Nodes executed: {' → '.join(stats['nodes'])}\n")
        return final_result


async def main():
    """Test orchestrator with streaming"""

    context_metadata = {"kb_id": "068dbcfd-ff20-7647-8000-c7cfdf551423"}
    web_search_config = WebSearchConfig(
        provider=SearchProvider.TAVILY,
        active=False,
        api_key=settings.tavily_api_key,
    )
    context_metadata.update({"web_search_config": web_search_config.model_dump()})

    logger.info("Initializing OrchestratorGraph...")
    orchestrator = OrchestratorGraph()

    human_message = HumanMessage(
        content="Analyze the geopolitical impact of the latest G7 summit decisions on energy trading.",
        additional_kwargs={"message_metadata": context_metadata},
    )
    conversation = [human_message]

    logger.info("OrchestratorGraph initialized successfully.\n")
    streamer = OrchestratorStreamer()
    await streamer.stream_orchestrator(orchestrator, conversation)


if __name__ == "__main__":
    asyncio.run(main())
