from src.agents.graph.research_graph import ResearchGraph
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime


class ResearchGraphStreamer:
    """Helper class to stream and visualize ResearchGraph execution"""

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

        Args:
            research_graph: ResearchGraph instance
            input_state: Initial state with contextualized_query

        Returns:
            The final state of the graph after execution.
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
            kind = event["event"]
            name = event.get("name", "")

            if kind == "on_chain_start":
                if any(
                    node_name in name
                    for node_name in [
                        "query_planner",
                        "search_executor",
                        "process_results",
                        "verification_agent",
                        "dynamic_query_generator",
                        "reflection_node",
                        "pre_flight_rag_check",
                    ]
                ):
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

                    output = event.get("data", {}).get("output", {})
                    self._print_node_summary(name, output, duration)

                if name == "LangGraph":
                    final_state = event.get("data", {}).get("output")

            elif kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]

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

        self._print_final_summary(stats)
        return final_state

    def _print_node_summary(
        self, node_name: str, output: Dict[str, Any], duration: float
    ):
        """Print summary of node execution"""
        print(f"\n✅ {node_name} completed in {duration:.2f}s")
        if "query_planner" in node_name:
            pending = output.get("pending_queries", [])
            print(f"   📋 Generated {len(pending)} queries")
        elif "search_executor" in node_name:
            search_result = output.get("search_results", {})
            search_type = search_result.get("search_type", "N/A")
            doc_count = len(search_result.get("documents", []))
            print(f"   🔍 Search Type: {search_type.upper()}, Documents: {doc_count}")
        elif "process_results" in node_name:
            knowledge_len = len(output.get("accumulated_knowledge", ""))
            should_retry = output.get("should_retry_query", False)
            print(f"   📚 Knowledge size: {knowledge_len} chars")
            print(f"   🔄 Should retry: {should_retry}")
        elif "verification_agent" in node_name:
            verification = output.get("verification_result", {})
            is_sufficient = verification.get("is_sufficient", False)
            confidence = verification.get("confidence", "N/A")
            missing = len(verification.get("missing_aspects", []))
            print(f"   ✓ Sufficient: {is_sufficient}, Confidence: {confidence}")
            print(f"   ❓ Missing aspects: {missing}")
        elif "dynamic_query_generator" in node_name:
            new_queries = output.get("pending_queries", [])
            print(f"   🎯 New queries generated: {len(new_queries)}")

    def _print_final_summary(self, stats: Dict[str, Any]):
        """Print final execution summary"""
        self._print_box("📊 RESEARCH GRAPH SUMMARY", color="green")

        print(f"Nodes executed: {len(stats['nodes_executed'])}")
        print(f"   └─ {', '.join(stats['nodes_executed'][:5])}...")
        print(f"\nSearches performed: {stats['searches_performed']}")
        print(f"   ├─ RAG: {stats['rag_searches']}")
        print(f"   └─ Web: {stats['web_searches']}")
        print(f"\nTool calls: {stats['tool_calls']}")
        print(f"Tokens streamed: {stats['tokens_streamed']}")

        if self.node_timings:
            print("\n⏱️   Node Timings:")
            for node, duration in sorted(
                self.node_timings.items(), key=lambda x: x[1], reverse=True
            )[:5]:
                print(f"   • {node}: {duration:.2f}s")


async def main():
    """Example usage"""
    research_graph = ResearchGraph()

    input_state = {
        "contextualized_query": "report to me about the recent storm of vietnam",
        "context_metadata": {"kb_id": "068dbcfd-ff20-7647-8000-c7cfdf551423"},
    }
    streamer = ResearchGraphStreamer()
    final_result = await streamer.stream_research(research_graph, input_state)

    print("\n" + "=" * 60)
    print("Getting final result...")

    if final_result:
        print(
            f"\n📝 Final Knowledge Length: {len(final_result.get('accumulated_knowledge', ''))} chars"
        )
        print(f"✅ Total Iterations: {final_result.get('iteration_count', 0)}")
    else:
        print("Could not retrieve the final result.")


if __name__ == "__main__":
    asyncio.run(main())
