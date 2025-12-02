import asyncio

import aiohttp

# ==========================================
# CẤU HÌNH (CONFIGURATION)
# ==========================================
API_BASE_URL = "http://localhost:8000"
API_KEY = "hapt68"
USER_ID = "hafizh"
APP_NAME = "single_query_test"

TARGET_KB_ID = "06926eb4-af94-7355-8000-765cda3cfeec"
TARGET_QUERY = """Trong multimodal QA: vì sao văn bản không đủ để trả lời câu hỏi từ ảnh, có bao nhiêu user đang hoạt động trong hệ thống? dùng deep search"""
USE_AGENT = False
# ==========================================

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


async def create_conversation(session: aiohttp.ClientSession) -> str:
    """Tạo một conversation mới và trả về conversation_id"""
    url = f"{API_BASE_URL}/conversation/create"
    params = {"app_name": APP_NAME}

    print("🔄 Creating conversation...")
    async with session.post(url, params=params, headers=HEADERS) as response:
        if response.status != 200:
            text = await response.text()
            raise Exception(
                f"Failed to create conversation: {response.status} - {text}"
            )

        data = await response.json()
        # Xử lý trường hợp data bọc trong data hoặc không
        conv_id = data.get("data", data).get("conversation_id")
        print(f"✅ Conversation created: {conv_id}")
        return conv_id


async def ask_question(session: aiohttp.ClientSession, conversation_id: str):
    """Gửi câu hỏi vào conversation đã tạo"""
    url = f"{API_BASE_URL}/chat/ask"

    payload = {
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": TARGET_QUERY}],
            "metadata": {
                "conversation_id": conversation_id,
                "kb_id": TARGET_KB_ID,
                "user_id": USER_ID,
            },
        },
        "agentic": USE_AGENT,
        "web_search": False,
    }

    print(f"📤 Sending query: '{TARGET_QUERY}'...")

    try:
        async with session.post(url, json=payload, headers=HEADERS) as response:
            if response.status != 200:
                text = await response.text()
                print(f"❌ Error {response.status}: {text}")
                return

            data = await response.json()
            actual_data = data.get("data", data)

            # --- Parse câu trả lời ---
            answer_text = ""
            for part in actual_data.get("parts", []):
                if part.get("type") == "text":
                    answer_text += part.get("text", "")

            # --- Parse Contexts (Tài liệu tham khảo) ---
            contexts = []
            chunks = actual_data.get("retrieval_context", {}).get("cited_chunks", [])
            for chunk in chunks:
                content = (
                    chunk.get("page_content", "")
                    if isinstance(chunk, dict)
                    else getattr(chunk, "page_content", "")
                )
                if content:
                    contexts.append(content)

            # --- In kết quả ---
            print("\n" + "=" * 50)
            print("🤖 RESPONSE FROM SERVER:")
            print("=" * 50)
            print(answer_text)
            print("\n" + "-" * 50)
            print(f"📚 Contexts retrieved: {len(contexts)}")
            for idx, ctx in enumerate(contexts[:3]):  # In thử 3 context đầu
                print(f"  [{idx + 1}] {ctx[:100]}...")
            print("=" * 50)

    except Exception as e:
        print(f"❌ Exception occurred: {e}")


async def main():
    async with aiohttp.ClientSession() as session:
        try:
            # 1. Tạo conversation
            conversation_id = await create_conversation(session)

            # 2. Gửi câu hỏi
            await ask_question(session, conversation_id)

        except Exception as e:
            print(f"🛑 Critical Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
