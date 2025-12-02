# tests/intergration_test/main_graph_test.py
import asyncio
import time

from langchain_core.messages import HumanMessage
from langchain_core.runnables.schema import StreamEvent

from src.agents.main_graph import MainGraph
from src.core.config.settings import settings
from src.utils.logger_conf import logger


class MainGraphStreamer:
    """Helper class to visualize streaming from MainGraph"""

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

    async def stream_orchestrator(self, orchestrator: MainGraph, conversation: list):
        """Stream MainGraph execution with visual feedback"""

        self._print_box("🚀 STARTING MAIN GRAPH", color="cyan")
        print(f"📝 Query: {conversation[-1].content}\n")

        llm_buffer = ""
        final_result = None

        is_graph_completed = False

        stats = {"nodes": [], "tokens": 0, "tools": 0, "start_time": time.time()}

        async for event in orchestrator.astream(conversation):
            event: StreamEvent
            kind = event["event"]
            name = event.get("name", "")

            if kind == "on_chain_start":
                stats["nodes"].append(name)
                if name in ["ThinkingGraph", "NormalGraph", "MainGraph"]:
                    self._print_box(f"🔄 Graph: {name}", color="cyan")
                else:
                    self._print_box(f"🔄 NODE: {name}", color="blue")

            elif kind == "on_chain_end":
                output = event.get("data", {}).get("output")

                if name == "MainGraph" and not is_graph_completed:
                    is_graph_completed = True
                    final_result = output
                    continue

                self._print_box(f"✅ Graph: {name} COMPLETED", color="green")
                continue

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

    context_metadata = {
        "kb_id": "06926eb4-af94-7355-8000-765cda3cfeec",
        "db_url": settings.database_url,
        "allow_tables": ["conversations", "documents", "knowledge_bases", "users"],
    }
    logger.info("Initializing OrchestratorGraph...")
    orchestrator = MainGraph()

    human_message_1 = HumanMessage(
        content="""Tìm cho tôi thông tin vì sao LMM thường sai khi đếm vật trong ảnh, sau đó check xem có bao nhiêu user đang hoạt động trong hệ thống?""",
        additional_kwargs=context_metadata,
    )

    # # # Mô phỏng response từ model
    # ai_response_1 = AIMessage(
    #     content="Xin lỗi, tôi không có thông tin cụ thể về tổng số cuộc hội thoại hiện tại. Bạn có thể cung cấp thêm chi tiết hoặc làm rõ câu hỏi của bạn không?"
    # )

    # # # Turn 2: Câu hỏi vague thứ 2 (giống turn 1 nhưng hơi khác)
    # human_message_2 = HumanMessage(
    #     content="Tôi cần biết hiện trong database có bao nhiêu cuộc trò chuyện. Cũng như là tổng số user đang sử dụng hệ thống.",
    #     additional_kwargs=context_metadata,
    # )

    # Xây dựng conversation history
    conversation = [
        human_message_1,
        # ai_response_1,
        # human_message_2,  # Câu hỏi vague lần 2
    ]

    logger.info("OrchestratorGraph initialized successfully.\n")
    streamer = MainGraphStreamer()
    await streamer.stream_orchestrator(orchestrator, conversation)


if __name__ == "__main__":
    asyncio.run(main())
