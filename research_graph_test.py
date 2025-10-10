from src.agents.graph.research_graph import ResearchGraph
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from langchain_core.runnables.schema import StreamEvent


class ResearchGraphStreamer:
    def __init__(self):
        self.node_timings: Dict[str, float] = {}
        self.node_start_times: Dict[str, float] = {}
        self.llm_token_count = 0
        self.tool_calls_count = 0

    def _get_timestamp(self) -> str:
        """Get formatted timestamp"""
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]

    def _print_box(self, title: str, content: str = "", color: str = "blue"):
        """Print colored box"""
        colors = {
            "blue": "\033[94m",
            "green": "\033[92m",
            "yellow": "\033[93m",
            "red": "\033[91m",
            "cyan": "\033[96m",
            "magenta": "\033[95m",
            "reset": "\033[0m",
        }

        c = colors.get(color, colors["blue"])
        reset = colors["reset"]

        print(f"\n{c}{'=' * 60}{reset}")
        print(f"{c}║ {title}{reset}")
        if content:
            print(f"{c}║{reset} {content}")
        print(f"{c}{'=' * 60}{reset}")

    async def stream_research(
        self, research_graph: "ResearchGraph", input_state: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Stream research graph execution with detailed insights and return the final state.
        """
        self._print_box("🚀 STARTING RESEARCH GRAPH", color="cyan")
        print(f"📝 Query: {input_state.get('contextualized_query', 'N/A')}")

        llm_streaming_buffer = ""
        final_state = None

        stats = {
            "nodes_executed": [],
            "searches_performed": 0,
            "rag_searches": 0,
            "web_searches": 0,
            "tool_calls": 0,
            "tokens_streamed": 0,
        }

        config = {"recursion_limit": 100}

        async for event in research_graph.graph.astream_events(
            input_state, config=config, version="v2"
        ):
            event: StreamEvent
            kind = event["event"]
            name = event.get("name", "")

            if kind == "on_chain_start":
                self.node_start_times[name] = asyncio.get_event_loop().time()
                stats["nodes_executed"].append(name)

                self._print_box(
                    f"🔄 NODE: {name}",
                    f"Timestamp: {self._get_timestamp()}",
                    color="blue",
                )

            elif kind == "on_chain_end":
                if name in self.node_start_times:
                    duration = (
                        asyncio.get_event_loop().time() - self.node_start_times[name]
                    )
                    self.node_timings[name] = duration

                if name == "LangGraph":
                    final_state = event.get("data", {}).get("output")

            elif kind == "on_chat_model_stream":
                chunk = event.data.chunk

                if chunk.content:
                    print(chunk.content, end="", flush=True)
                    llm_streaming_buffer += chunk.content
                    stats["tokens_streamed"] += 1

                if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                    for tc_chunk in chunk.tool_call_chunks:
                        tool_name = tc_chunk.get("name", "")
                        tool_args = tc_chunk.get("args", {})
                        if tool_name:
                            print(f"\n🔧 [Tool Call: {tool_name}]", flush=True)
                            stats["tool_calls"] += 1
                        print(tool_args, end="", flush=True)

            elif kind == "on_chat_model_end":
                if llm_streaming_buffer:
                    print()
                    llm_streaming_buffer = ""

            elif kind == "on_tool_start":
                tool_name = event.get("name", "")
                print(f"\n🔨 Tool Starting: {tool_name}")

                if "search" in tool_name.lower():
                    stats["searches_performed"] += 1
                    if "rag" in tool_name.lower():
                        stats["rag_searches"] += 1
                    elif "web" in tool_name.lower():
                        stats["web_searches"] += 1

            elif kind == "on_tool_end":
                tool_output = event.get("data", {}).get("output", "")
                output_preview = str(tool_output)[:100] if tool_output else "No output"
                print(f"✅ Tool Completed: {output_preview}...")

        return final_state


async def main():
    """Example usage"""
    research_graph = ResearchGraph()

    input_state = {
        "contextualized_query": "report to me about the recent storm of vietnam",
        "context_metadata": {"kb_id": "068dbcfd-ff20-7647-8000-c7cfdf551423"},
    }
    streamer = ResearchGraphStreamer()
    final_result = await streamer.stream_research(research_graph, input_state)
    print(f"Final result: {final_result}")


if __name__ == "__main__":
    asyncio.run(main())
