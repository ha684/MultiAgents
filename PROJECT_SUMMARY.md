# Project Summary

## 1. Project Overview
Dự án là một **Hệ thống Trợ lý Nghiên cứu AI (Agent Research System)** thông minh, được thiết kế để hoạt động như một Knowledge Management System (KMS) tiên tiến. Hệ thống có khả năng tự động định tuyến câu hỏi, tìm kiếm thông tin từ nhiều nguồn (nội bộ, web, database), và tổng hợp câu trả lời có trích dẫn (citation) minh bạch thông qua cơ chế Multi-Agent Orchestration.

## 2. Problem Statement
Giải quyết vấn đề phân mảnh kiến thức trong doanh nghiệp và khó khăn trong việc tổng hợp thông tin chính xác từ nhiều nguồn dữ liệu khác nhau (tài liệu phi cấu trúc, cơ sở dữ liệu có cấu trúc, và thông tin web). Hệ thống khắc phục hạn chế của các chatbot truyền thống bằng cách cung cấp khả năng suy luận sâu (reasoning), minh bạch nguồn tin và truy xuất dữ liệu chính xác.

## 3. Solution Approach
Sử dụng kiến trúc **Orchestrator-Workers** với LangGraph để điều phối luồng xử lý. Hệ thống chia làm hai chế độ chính:
- **Normal Mode:** Xử lý nhanh các câu hỏi đơn giản theo luồng tuyến tính.
- **Thinking Mode (Deep Research):** Xử lý các yêu cầu phức tạp bằng quy trình lặp (iterative) lấy cảm hứng từ tư duy của con người (lên kế hoạch -> thực hiện -> đánh giá -> lặp lại).

## 4. Technical Architecture

### 4.1 Tech Stack
- **Backend:** Python 3.13+, FastAPI, Uvicorn.
- **AI/ML:** LangGraph, LangChain, LiteLLM (Claude/GPT), FastEmbed, HuggingFace.
- **Database:** PostgreSQL (Metadata/Structured data), Qdrant (Vector DB), Redis (Caching), MinIO (Object Storage).
- **Other:** Docker, Celery (Async tasks), Alembic (Migrations), Graphiti (Knowledge Graph).

### 4.2 RAG Architecture
Hệ thống triển khai **Agentic RAG** kết hợp với **Hybrid Search**:
- **Embeddings:** Sử dụng FastEmbed/HuggingFace models qua API inference.
- **Vector Database:** Qdrant lưu trữ vector embeddings.
- **Retrieval Strategy:** Semantic search kết hợp Reranking (sử dụng Cross-Encoders) để tối ưu độ liên quan.
- **Chunking:** Hỗ trợ nhiều chiến lược: Naive chunking cho văn bản, Spreadsheet chunking cho Excel, và Image processing.
- **Knowledge Graph:** Tích hợp Graphiti để lưu trữ và truy xuất mối quan hệ giữa các thực thể.

### 4.3 Agent System
Hệ thống sử dụng **Multi-Agent System** điều phối bởi `MainGraph`:

**Orchestrator Agents:**
- **MainGraph:** Entry point, quyết định routing giữa Direct Response, Normal Mode, hoặc Thinking Mode.
- **NormalGraph:** Quản lý luồng xử lý nhanh (Single-shot).
- **ThinkingGraph:** Quản lý luồng nghiên cứu sâu (Iterative loop).

**Worker Agents:**
- **DirectionGenerationAgent:** Phân tích câu hỏi và xác định subgraph/query phù hợp (dùng trong NormalGraph).
- **PhaseAgent:** Lập kế hoạch cho từng bước nghiên cứu (đặt title, chọn hành động) trong ThinkingGraph.
- **ActionExecutionAgent:** Thực thi hành động: suy luận nội tại (reasoning) hoặc gọi công cụ (tool calling).
- **VerificationAgent:** Đánh giá tính đầy đủ của thông tin thu thập được, quyết định dừng hoặc tiếp tục lặp.
- **ResponseAgent:** Tổng hợp câu trả lời cuối cùng từ context và reasoning, đảm bảo văn phong và format.
- **CompressAgent:** Tóm tắt và nén nội dung từ các tài liệu tìm được để tiết kiệm context window.

**Specialized Subgraphs (Tools):**
- **Web Search Graph:** Tìm kiếm thông tin công khai (Tavily/Firecrawl).
- **RAG Search Graph:** Tìm kiếm tài liệu nội bộ (Qdrant).
- **SQL Query Graph:** Truy vấn dữ liệu có cấu trúc (PostgreSQL) với khả năng tự sinh SQL.

**Agent Coordination:**
Các agents giao tiếp thông qua `Shared State` trong LangGraph. Orchestrator chuyển trạng thái (state) chứa lịch sử hội thoại và kết quả trung gian giữa các node để các agent xử lý tuần tự hoặc song song.

### 4.4 Key Components
- **SubgraphRegistry:** Quản lý đăng ký và cấu hình động cho các subgraphs (tương tự pattern của Parlant).
- **ConversationService:** Quản lý phiên làm việc và lịch sử chat.
- **ExecutionManager:** Theo dõi và quản lý vòng đời thực thi của request.

## 5. Implemented Features

### 5.1 Core Features
1. **Intelligent Routing:** Tự động phân loại câu hỏi để chọn chiến lược xử lý tối ưu (Direct/Web/RAG/SQL).
2. **Deep Research (Thinking Mode):** Quy trình nghiên cứu đa bước, tự động sửa lỗi và tìm kiếm bổ sung khi thiếu thông tin.
3. **Multi-source Search:** Tìm kiếm đồng thời trên Web, Database và Tài liệu nội bộ.
4. **Citation & Transparency:** Hiển thị nguồn trích dẫn chính xác (số trang, tên file) cho từng ý trong câu trả lời.
5. **File Processing:** Hỗ trợ upload và xử lý nhiều định dạng (PDF, Docx, Excel, Images).

### 5.2 AI Capabilities
1. **Adaptive Reasoning:** Khả năng tự "suy nghĩ" (internal reasoning) để lập luận trước khi tìm kiếm hoặc trả lời.
2. **Self-Correction:** Tự động phát hiện lỗi khi thực thi tool (ví dụ: lỗi SQL, không tìm thấy doc) và thử lại với chiến lược khác.
3. **SQL Generation:** Chuyển đổi câu hỏi tự nhiên thành truy vấn SQL để lấy số liệu báo cáo.
4. **Cross-Modal Understanding:** Hiểu và xử lý thông tin từ cả văn bản và hình ảnh.

## 6. Technical Highlights
- **Iterative "Thinking" Loop:** Implement quy trình lặp giống tư duy con người để giải quyết vấn đề phức tạp, thay vì chỉ retrieval đơn thuần.
- **Dynamic Subgraph Loading:** Kiến trúc Registry cho phép thêm/bớt các nguồn dữ liệu/công cụ mới dễ dàng.
- **Content Hashing & Deduplication:** Cơ chế hash để loại bỏ tài liệu trùng lặp, tối ưu context window.
- **Hybrid Response Modes:** Hỗ trợ nhiều định dạng trả lời: Text thuần, SQL result view, hoặc Reasoning only.
- **Robust Error Handling:** Cơ chế fallback thông minh khi một subgraph thất bại.

## 7. Data Flow
1. **User Input** -> **MainGraph** (Router).
2. Router quyết định Mode:
   - **Direct:** LLM trả lời ngay.
   - **Normal:** Generate Direction -> Chọn Subgraph (Web/RAG/SQL) -> Execute -> Synthesize.
   - **Thinking:** Loop [Phase Plan -> Action (Reason/Tool) -> Execute -> Evaluate] -> Synthesize.
3. **Synthesize:** Tổng hợp thông tin từ `accumulated_context` + `internal_reasoning`.
4. **Output:** Câu trả lời cuối cùng kèm Metadata và Citations.

## 8. Key Statistics
- **Supported Subgraphs:** 3 (Web, RAG, SQL).
- **Agent Types:** 6+ core agents.
- **Database:** Hybrid (Relational + Vector).
- **Architecture:** Modular Graph-based (LangGraph).

