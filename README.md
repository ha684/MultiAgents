<div align="center">

<h1 align="center">
  <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f9e0.png" width="40" height="40">
  Agent Research System
</h1>

<p>
  🚀 A next-generation AI research agent powered by
  <a href="https://langchain-ai.github.io/langgraph/">LangGraph</a><br/>
  Understands questions, plans searches, and generates citation-backed answers.
</p>

</div>

---

## 🌟 Mục tiêu

Hệ thống này giúp bạn **nghiên cứu tự động** với quy trình như con người:
1. 🧠 Hiểu câu hỏi  
2. 🔍 Lập kế hoạch tìm kiếm  
3. 📚 Tổng hợp thông tin đáng tin cậy  
4. 🧩 Viết câu trả lời có trích dẫn rõ ràng  
5. ✋ Tạm dừng & can thiệp bất kỳ lúc nào  

---

## 🧩 Kiến trúc tổng quan

```mermaid
flowchart LR
    A[👤 User] --> B[🕹️ Orchestrator]
    B --> C[🔍 Query Planning]
    C --> D[🧠 Answer Generation]
    D --> E[📤 Final Answer]
    E --> A
````

---

## ✨ Tính năng nổi bật

* ⚙️ **Automation by default — intervention on demand**
* ⚡ **Parallel query execution**
* 📚 **Citation-aware synthesis**
* 🧠 **Self-critique & quality evaluation loop**
* 🧭 **Composable LangGraphs**


---

## 🧠 Tech Stack

| Thành phần         | Mô tả                                   |
| ------------------ | --------------------------------------- |
| 🧩 **LangGraph**   | Xây pipeline đa agent có state          |
| 🔗 **LangChain**   | Orchestrate LLMs & tools                |
| 🌐 **Search APIs** | Web / docs / academic search            |
| 🧠 **LLMs**        | OpenAI / Anthropic (pluggable) |

---

<div align="center">

<img src="https://github.com/user-attachments/assets/ai-loop.gif" width="340" alt="AI Agent Loop Animation"><br> <i>"The best research agents don’t just find answers — they understand questions."</i>

</div>