from src.llm.factory import get_llm
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, ToolMessage


@tool
def think(thought: str) -> str:
    """Use this tool for strategic reasoning, planning, and verification throughout your task execution process... (giữ nguyên docstring)"""
    print(
        f"\n--- THOUGHT PROCESS (EXECUTED BY CODE) ---\n{thought}\n------------------------------------------"
    )
    return "Thought process has been recorded and acknowledged. Ready to generate the final answer."


# --- Thiết lập ban đầu (giống như trước) ---
system_prompt = """You are a helpful assistant. You MUST use the `think` tool first to outline your plan and reasoning for any user request. 
Do not provide a direct answer until you have used the `think` tool to break down the problem.
Your thought process should include:
1.  Understanding the user's core question.
2.  Planning the steps to construct a comprehensive answer.
3.  Identifying the key pieces of information needed for the final response.
"""

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        ("human", "{user_input}"),
    ]
)

llm = get_llm("nxchat")
llm_with_tools = llm.bind_tools([think])
chain = prompt | llm_with_tools

# --- BẮT ĐẦU VÒNG LẶP XỬ LÝ TOOL ---

# Bước 1 & 2: Gửi yêu cầu ban đầu và nhận về tool call
user_question = "I want to know about the history of the universe"
print(f"User Question: {user_question}\n")

# Lưu lại lịch sử hội thoại
messages = [HumanMessage(content=user_question)]

# Gọi chain lần đầu
first_response = chain.invoke({"user_input": user_question})
messages.append(first_response)  # Thêm phản hồi của AI (chứa tool_calls) vào lịch sử

print("--- AI First Response (Requesting Tool Call) ---")
print(first_response)
print("--------------------------------------------------\n")


# Bước 3: Kiểm tra xem LLM có yêu cầu gọi tool không và thực thi nó
if first_response.tool_calls:
    # Danh sách các tool có sẵn để thực thi
    available_tools = {"think": think}

    # Chuẩn bị để lưu kết quả từ tool
    tool_outputs = []

    for tool_call in first_response.tool_calls:
        tool_name = tool_call["name"]
        if tool_name in available_tools:
            # Lấy hàm tool tương ứng
            tool_to_call = available_tools[tool_name]
            # Lấy đối số và thực thi tool
            tool_args = tool_call["args"]
            tool_result = tool_to_call.invoke(tool_args)

            # Bước 4: Đóng gói kết quả vào ToolMessage
            tool_outputs.append(
                ToolMessage(content=str(tool_result), tool_call_id=tool_call["id"])
            )

    # Thêm tất cả các kết quả tool vào lịch sử
    messages.extend(tool_outputs)

    print("--- Tool Outputs (Sending back to AI) ---")
    print(tool_outputs)
    print("--------------------------------------------\n")

    # Bước 5: Gọi lại LLM với lịch sử hội thoại đã được cập nhật
    print("--- AI Final Response (After Thinking) ---")
    # Lần này chúng ta không dùng `chain` nữa mà gọi trực tiếp `llm_with_tools`
    # với toàn bộ lịch sử messages
    final_answer = llm_with_tools.invoke(messages)
    print(final_answer.content)
    print("------------------------------------------")

else:
    # Nếu LLM trả lời trực tiếp mà không dùng tool
    print("--- AI Direct Response ---")
    print(first_response.content)
    print("--------------------------")
