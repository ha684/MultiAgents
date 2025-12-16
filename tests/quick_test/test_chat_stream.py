# tests/test_chat_stream.py
"""
Test script for Chat Streaming via WebSocket

This script demonstrates the full flow:
1. Create a chat task via POST /chat/ask/task
2. Connect to WebSocket /chat/stream/{task_id}
3. Receive streaming events
4. Handle reconnection with last_event_id
5. Send stop command to cancel

Usage:
    python tests/test_chat_stream.py

Requirements:
    pip install websockets httpx
"""

import asyncio
import json

import httpx
import websockets

# Configuration
BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"
AUTH_TOKEN = "hapt68"  # Replace with valid token

# Test data - replace with your actual IDs
TEST_CONVERSATION_ID = "06941298-5419-71fa-8000-89388ba7d174"
TEST_USER_ID = "hafizh"
TEST_KB_ID = "0694019d-ebb1-7895-8000-ce0eb4bad4cd"


class ChatStreamTester:
    def __init__(self):
        self.task_id = None
        self.last_event_id = None
        self.accumulated_content = ""
        self.accumulated_thinking = ""
        self.is_cancelled = False
        self.events_received = []

    async def create_task(
        self,
        message: str,
        agentic: bool = False,
        web_search: bool = False,
    ) -> str | None:
        """Create a chat task and return task_id"""
        print(f"\n{'=' * 60}")
        print("📤 Creating chat task...")
        print(f"   Message: {message[:50]}...")
        print(f"   Agentic: {agentic}, Web Search: {web_search}")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/chat/ask/task",
                json={
                    "conversation_id": TEST_CONVERSATION_ID,
                    "user_id": TEST_USER_ID,
                    "kb_id": TEST_KB_ID,
                    "message_text": message,
                    "message_metadata": {},
                    "agentic": agentic,
                    "web_search": web_search,
                },
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
                timeout=30.0,
            )

            if response.status_code == 200:
                data = response.json()
                self.task_id = data["data"]["task_id"]
                print(f"✅ Task created: {self.task_id}")
                print(f"   WebSocket URL: {data['data']['websocket_url']}")
                return self.task_id
            else:
                print(f"❌ Failed to create task: {response.status_code}")
                print(f"   Error: {response.text}")
                return None

    async def stream_via_websocket(
        self,
        task_id: str,
        resume_from: str | None = None,
    ):
        """Connect to WebSocket and stream events"""
        ws_url = f"{WS_URL}/websocket/stream/{task_id}"
        if resume_from:
            ws_url += f"?last_event_id={resume_from}"

        print(f"\n{'=' * 60}")
        print("🔌 Connecting to WebSocket...")
        print(f"   URL: {ws_url}")

        try:
            async with websockets.connect(
                ws_url,
                additional_headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
            ) as ws:
                print("✅ Connected!")

                async for message in ws:
                    event = json.loads(message)
                    await self.handle_event(event)

                    if event.get("type") in ["message_stop", "error", "cancelled"]:
                        break

        except websockets.ConnectionClosed as e:
            print(f"\n⚠️  Connection closed: {e}")
            if self.last_event_id and not self.is_cancelled:
                print(f"   Last event ID: {self.last_event_id}")
                print("   You can reconnect with this ID to resume")

        except Exception as e:
            print(f"\n❌ WebSocket error: {e}")

    async def handle_event(self, event: dict):
        """Process incoming WebSocket event"""
        event_type = event.get("type")
        event_id = event.get("event_id")
        data = event.get("data", {})

        if event_id:
            self.last_event_id = event_id

        self.events_received.append(event)

        if event_type == "connected":
            print("\n📡 Connected event received")
            print(f"   Task ID: {data.get('task_id')}")
            print(f"   Status: {data.get('status')}")

        elif event_type == "message_start":
            print("\n🚀 Message generation started")

        elif event_type == "content_block_delta":
            delta = data.get("delta", {})
            delta_type = delta.get("type")
            text = delta.get("text", "")

            if delta_type == "text_delta":
                self.accumulated_content += text
                print(text, end="", flush=True)

            elif delta_type == "thinking_delta":
                self.accumulated_thinking += text
                print(f"\033[90m{text}\033[0m", end="", flush=True)

        elif event_type == "status":
            phase = data.get("phase")
            message = data.get("message")
            progress = data.get("progress")
            metadata = data.get("metadata", {})

            print(f"\n📊 Status: [{phase}] {message}", end="")
            if progress is not None:
                print(f" ({progress * 100:.0f}%)", end="")
            if metadata.get("sources_count"):
                print(f" - {metadata['sources_count']} sources", end="")
            print()

        elif event_type == "message_stop":
            print(f"\n\n{'=' * 60}")
            print("✅ Stream complete!")
            references = data.get("references", [])
            if references:
                print(f"   References: {len(references)} sources")
            metadata = data.get("metadata", {})
            if metadata:
                print(f"   Metadata: {json.dumps(metadata, indent=2)[:200]}...")

        elif event_type == "error":
            print(f"\n❌ Error: {data.get('type')} - {data.get('message')}")

        elif event_type == "cancelled":
            print(f"\n⚠️  Task cancelled: {data.get('message')}")
            self.is_cancelled = True

        elif event_type == "pong":
            print("\n🏓 Pong received")

    async def send_stop_command(self, ws):
        """Send stop command via WebSocket"""
        print("\n🛑 Sending stop command...")
        await ws.send(json.dumps({"action": "stop"}))

    async def send_ping(self, ws):
        """Send ping command via WebSocket"""
        await ws.send(json.dumps({"action": "ping"}))

    async def get_task_status(self, task_id: str) -> dict | None:
        """Get task status via API"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/chat/task/{task_id}/status",
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
            )
            if response.status_code == 200:
                return response.json()
            return None

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel task via API"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/chat/task/{task_id}/cancel",
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
            )
            return response.status_code == 200

    def print_summary(self):
        """Print test summary"""
        print(f"\n{'=' * 60}")
        print("📋 TEST SUMMARY")
        print(f"{'=' * 60}")
        print(f"Task ID: {self.task_id}")
        print(f"Events received: {len(self.events_received)}")
        print(f"Content length: {len(self.accumulated_content)} chars")
        print(f"Thinking length: {len(self.accumulated_thinking)} chars")
        print(f"Last event ID: {self.last_event_id}")
        print(f"Cancelled: {self.is_cancelled}")


async def test_basic_stream():
    """Test basic streaming flow"""
    print("\n" + "=" * 60)
    print("🧪 TEST: Basic Streaming")
    print("=" * 60)

    tester = ChatStreamTester()

    task_id = await tester.create_task(
        message="What is machine learning? Explain briefly.",
        agentic=False,
    )

    if not task_id:
        print("❌ Test failed: Could not create task")
        return

    await tester.stream_via_websocket(task_id)

    tester.print_summary()


async def test_agentic_stream():
    """Test agentic mode with thinking"""
    print("\n" + "=" * 60)
    print("🧪 TEST: Agentic Mode with Thinking")
    print("=" * 60)

    tester = ChatStreamTester()

    task_id = await tester.create_task(
        message="Research and compare Python vs JavaScript for web development",
        agentic=True,
    )

    if not task_id:
        print("❌ Test failed: Could not create task")
        return

    await tester.stream_via_websocket(task_id)

    tester.print_summary()

    if tester.accumulated_thinking:
        print("\n💭 Thinking content preview:")
        print(f"   {tester.accumulated_thinking[:200]}...")


async def test_reconnection():
    """Test reconnection with last_event_id"""
    print("\n" + "=" * 60)
    print("🧪 TEST: Reconnection")
    print("=" * 60)

    tester = ChatStreamTester()

    task_id = await tester.create_task(
        message="Tell me a long story about a robot learning to paint",
        agentic=False,
    )

    if not task_id:
        print("❌ Test failed: Could not create task")
        return

    print("\n📡 First connection (will disconnect after 2 seconds)...")

    ws_url = f"{WS_URL}/websocket/stream/{task_id}"

    try:
        async with websockets.connect(
            ws_url,
            additional_headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        ) as ws:
            try:
                async with asyncio.timeout(2.0):
                    async for message in ws:
                        event = json.loads(message)
                        await tester.handle_event(event)
            except asyncio.TimeoutError:
                print("\n\n⏱️  Simulating disconnect after 2 seconds...")

    except Exception as e:
        print(f"Error: {e}")

    if tester.last_event_id:
        print(f"\n📡 Reconnecting from event: {tester.last_event_id}")
        await asyncio.sleep(1)

        await tester.stream_via_websocket(
            task_id,
            resume_from=tester.last_event_id,
        )

    tester.print_summary()


async def test_cancellation():
    """Test task cancellation"""
    print("\n" + "=" * 60)
    print("🧪 TEST: Cancellation")
    print("=" * 60)

    tester = ChatStreamTester()

    # Create task
    task_id = await tester.create_task(
        message="Write a very long essay about the history of computing",
        agentic=False,
    )

    if not task_id:
        print("❌ Test failed: Could not create task")
        return

    # Connect and cancel after 3 seconds
    print("\n📡 Connecting (will cancel after 3 seconds)...")

    ws_url = f"{WS_URL}/websocket/stream/{task_id}"

    try:
        async with websockets.connect(
            ws_url,
            additional_headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        ) as ws:
            # Create cancel task
            async def cancel_after_delay():
                await asyncio.sleep(3.0)
                print("\n\n🛑 Sending stop command...")
                await ws.send(json.dumps({"action": "stop"}))

            cancel_task = asyncio.create_task(cancel_after_delay())

            # Read events
            async for message in ws:
                event = json.loads(message)
                await tester.handle_event(event)

                if event.get("type") in ["message_stop", "error", "cancelled"]:
                    cancel_task.cancel()
                    break

    except Exception as e:
        print(f"Error: {e}")

    tester.print_summary()


async def interactive_test():
    """Interactive test - type messages and see streaming responses"""
    print("\n" + "=" * 60)
    print("🎮 INTERACTIVE TEST")
    print("=" * 60)
    print("Type your message and press Enter.")
    print("Commands:")
    print("  /agentic - Toggle agentic mode")
    print("  /quit    - Exit")
    print("=" * 60)

    agentic_mode = False

    while True:
        print(f"\n[Agentic: {'ON' if agentic_mode else 'OFF'}]")
        user_input = input("You: ").strip()

        if not user_input:
            continue

        if user_input.lower() == "/quit":
            print("Goodbye!")
            break

        if user_input.lower() == "/agentic":
            agentic_mode = not agentic_mode
            print(f"Agentic mode: {'ON' if agentic_mode else 'OFF'}")
            continue

        tester = ChatStreamTester()

        task_id = await tester.create_task(
            message=user_input,
            agentic=agentic_mode,
        )

        if task_id:
            print("\nAssistant: ", end="")
            await tester.stream_via_websocket(task_id)


def main():
    """Main entry point"""
    print("=" * 60)
    print("🧪 CHAT STREAM TEST SUITE")
    print("=" * 60)
    print("\nSelect a test:")
    print("1. Basic streaming")
    print("2. Agentic mode (with thinking)")
    print("3. Reconnection test")
    print("4. Cancellation test")
    print("5. Interactive mode")
    print("6. Run all tests")

    choice = input("\nEnter choice (1-6): ").strip()

    if choice == "1":
        asyncio.run(test_basic_stream())
    elif choice == "2":
        asyncio.run(test_agentic_stream())
    elif choice == "3":
        asyncio.run(test_reconnection())
    elif choice == "4":
        asyncio.run(test_cancellation())
    elif choice == "5":
        asyncio.run(interactive_test())
    elif choice == "6":

        async def run_all():
            await test_basic_stream()
            await test_agentic_stream()
            await test_reconnection()
            await test_cancellation()

        asyncio.run(run_all())
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
