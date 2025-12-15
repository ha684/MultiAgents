# tests/quick_test/test_streaming.py
"""
Quick tests for the Kafka-backed LLM streaming pipeline.

Run with: python -m tests.quick_test.test_streaming
"""

import asyncio
import json
import sys
from typing import Optional

import httpx

BASE_URL = "http://localhost:8000"
AUTH_TOKEN = None  # Set this or use environment variable


async def get_auth_token() -> str:
    """Get or create an auth token for testing."""
    global AUTH_TOKEN
    if AUTH_TOKEN:
        return AUTH_TOKEN

    # Try to login or use a test token
    # For testing, you may need to create a user first
    print("Note: Set AUTH_TOKEN variable with a valid token")
    return "test_token"


async def test_start_completion():
    """Test starting a chat completion."""
    token = await get_auth_token()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "messages": [
                    {"role": "user", "content": "Write a short haiku about coding."}
                ],
                "use_rag": False,
            },
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Started completion: request_id={data['request_id']}")
            return data["request_id"]
        else:
            print(
                f"❌ Failed to start completion: {response.status_code} - {response.text}"
            )
            return None


async def test_sse_stream(request_id: str, last_event_id: Optional[str] = None):
    """Test SSE streaming with optional resume."""
    token = await get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    if last_event_id:
        headers["Last-Event-ID"] = last_event_id
        print(f"📡 Resuming SSE stream from cursor: {last_event_id}")
    else:
        print(f"📡 Starting SSE stream for request_id: {request_id}")

    events_received = []
    last_cursor = None

    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(
            "GET",
            f"{BASE_URL}/v1/chat/stream/{request_id}",
            headers=headers,
        ) as response:
            if response.status_code != 200:
                print(f"❌ Stream failed: {response.status_code}")
                return None, []

            buffer = ""
            async for chunk in response.aiter_text():
                buffer += chunk

                # Parse SSE events
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)

                    if event_str.startswith(":"):
                        # Comment/keepalive
                        continue

                    event = {}
                    for line in event_str.strip().split("\n"):
                        if line.startswith("id: "):
                            event["id"] = line[4:]
                            last_cursor = line[4:]
                        elif line.startswith("event: "):
                            event["event"] = line[7:]
                        elif line.startswith("data: "):
                            event["data"] = json.loads(line[6:])

                    if event:
                        events_received.append(event)
                        event_type = event.get("event", "message")

                        if event_type == "delta":
                            print(
                                event.get("data", {}).get("delta", ""),
                                end="",
                                flush=True,
                            )
                        elif event_type == "done":
                            print("\n✅ Stream completed")
                            return last_cursor, events_received
                        elif event_type == "error":
                            print(
                                f"\n❌ Stream error: {event.get('data', {}).get('message', 'Unknown error')}"
                            )
                            return last_cursor, events_received

    return last_cursor, events_received


async def test_stream_status(request_id: str):
    """Test getting stream status."""
    token = await get_auth_token()

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/v1/chat/status/{request_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        if response.status_code == 200:
            data = response.json()
            print(f"📊 Status: {data['status']}, cursor: {data.get('cursor', 'N/A')}")
            return data
        else:
            print(f"❌ Failed to get status: {response.status_code}")
            return None


async def test_resume_functionality():
    """Test the complete resume workflow."""
    print("\n" + "=" * 60)
    print("Testing Kafka-backed LLM Streaming with Resume")
    print("=" * 60)

    # Step 1: Start a completion
    print("\n📌 Step 1: Starting completion...")
    request_id = await test_start_completion()
    if not request_id:
        return

    # Step 2: Wait a bit for the task to start
    print("\n⏳ Waiting for task to start...")
    await asyncio.sleep(2)

    # Step 3: Check status
    print("\n📌 Step 3: Checking status...")
    await test_stream_status(request_id)

    # Step 4: Stream some events
    print("\n📌 Step 4: Starting SSE stream...")
    print("-" * 40)

    last_cursor, events = await test_sse_stream(request_id)

    print("-" * 40)
    print(f"Received {len(events)} events, last cursor: {last_cursor}")

    # Step 5: If we have a cursor, test resume
    if last_cursor and len(events) > 3:
        # Simulate disconnect by using cursor from middle of stream
        resume_cursor = events[len(events) // 2].get("id")

        print(f"\n📌 Step 5: Testing resume from cursor: {resume_cursor}")
        print("-" * 40)

        _, resume_events = await test_sse_stream(request_id, resume_cursor)

        print("-" * 40)
        print(f"Received {len(resume_events)} events after resume")

        if len(resume_events) < len(events):
            print("✅ Resume correctly skipped already-received events")
        else:
            print("⚠️ Resume may have replayed all events")

    # Step 6: Final status check
    print("\n📌 Step 6: Final status check...")
    await test_stream_status(request_id)

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


async def test_websocket_stream(request_id: str, cursor: Optional[str] = None):
    """Test WebSocket streaming."""
    import websockets

    token = await get_auth_token()

    print("🔌 Connecting to WebSocket...")

    async with websockets.connect(
        "ws://localhost:8000/v1/chat/ws",
        extra_headers={"Authorization": f"Bearer {token}"},
    ) as ws:
        # Send initial message
        await ws.send(
            json.dumps(
                {
                    "request_id": request_id,
                    "cursor": cursor,
                }
            )
        )

        last_cursor = None

        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                data = json.loads(msg)

                msg_type = data.get("type", "")

                if msg_type == "connected":
                    print("✅ Connected to stream")
                elif msg_type == "delta":
                    delta = data.get("data", {}).get("delta", "")
                    print(delta, end="", flush=True)
                    last_cursor = data.get("cursor")
                elif msg_type == "done":
                    print("\n✅ Stream completed")
                    break
                elif msg_type == "error":
                    print(f"\n❌ Error: {data.get('message', 'Unknown')}")
                    break
                elif msg_type == "ping":
                    pass  # Keepalive

            except asyncio.TimeoutError:
                print("⏳ Timeout waiting for message")
                break

        return last_cursor


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "start":
            asyncio.run(test_start_completion())
        elif sys.argv[1] == "stream" and len(sys.argv) > 2:
            request_id = sys.argv[2]
            cursor = sys.argv[3] if len(sys.argv) > 3 else None
            asyncio.run(test_sse_stream(request_id, cursor))
        elif sys.argv[1] == "status" and len(sys.argv) > 2:
            asyncio.run(test_stream_status(sys.argv[2]))
        elif sys.argv[1] == "ws" and len(sys.argv) > 2:
            request_id = sys.argv[2]
            cursor = sys.argv[3] if len(sys.argv) > 3 else None
            asyncio.run(test_websocket_stream(request_id, cursor))
        else:
            print("Usage:")
            print("  python -m tests.quick_test.test_streaming start")
            print(
                "  python -m tests.quick_test.test_streaming stream <request_id> [cursor]"
            )
            print("  python -m tests.quick_test.test_streaming status <request_id>")
            print(
                "  python -m tests.quick_test.test_streaming ws <request_id> [cursor]"
            )
    else:
        asyncio.run(test_resume_functionality())
