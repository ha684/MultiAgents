# Thiết kế Chi Tiết Agent Research System với LangGraph

## 1. Tổng Quan Kiến Trúc

**3 LangGraph riêng biệt** để tối ưu về modularity, maintainability và khả năng mở rộng:

### **Graph 1: Main Orchestrator Graph** (Graph điều phối chính)
- Nhận input từ user
- Quyết định flow chính của toàn bộ hệ thống
- Gọi các sub-graph khác khi cần
- Tổng hợp kết quả cuối cùng

### **Graph 2: Query Planning & Execution Graph** (Graph lập kế hoạch và thực thi)
- Phân tích câu hỏi
- Tạo kế hoạch tìm kiếm
- Thực thi các truy vấn
- Thu thập và xử lý kết quả

### **Graph 3: Answer Generation Graph** (Graph tạo câu trả lời)
- Phân tích nguồn thông tin
- Tổng hợp nội dung
- Tạo câu trả lời có trích dẫn
- Đánh giá chất lượng

---

## 2. Chi Tiết Từng Graph

## GRAPH 1: MAIN ORCHESTRATOR GRAPH

**Mục đích:** Điều phối toàn bộ flow, quản lý state tổng thể, quyết định khi nào cần pause để user can thiệp.

### State Schema:
```python
{
    "user_query": str,           # Câu hỏi gốc
    "conversation_history": list, # Lịch sử hội thoại
    "query_plan": dict,          # Kế hoạch từ Graph 2
    "search_results": list,      # Kết quả từ Graph 2
    "final_answer": str,         # Câu trả lời từ Graph 3
    "user_intervention": dict,   # User có chỉnh sửa kế hoạch không
    "current_stage": str,        # planning/searching/answering/completed
    "pause_requested": bool      # User có muốn pause không
}
```

### Các Node:

**Node 1.1: Input Processor**
- Nhận `user_query` và `conversation_history`
- Làm sạch input, chuẩn hóa
- Phát hiện ngôn ngữ (Vietnamese/English)
- Lưu vào state
- Output: State với `user_query` đã được xử lý

**Node 1.2: Routing Decision**
- Phân loại loại câu hỏi:
  - Simple factual (có thể trả lời trực tiếp từ knowledge)
  - Complex research (cần search và phân tích)
  - Follow-up question (liên quan đến câu hỏi trước)
- Quyết định có cần gọi Graph 2 không
- Output: `needs_research: bool`

**Node 1.3: Call Query Planning Graph**
- Gọi Graph 2 với input là `user_query`
- Nhận về `query_plan` (danh sách các truy vấn cần thực thi)
- Lưu `query_plan` vào state
- Set `current_stage = "planning"`
- Output: State có `query_plan`

**Node 1.4: User Intervention Checkpoint**
- Kiểm tra `pause_requested` hoặc `user_intervention`
- Nếu user muốn chỉnh sửa plan:
  - Pause execution
  - Trả về plan cho user qua UI
  - Chờ user edit hoặc approve
  - Nhận updated plan
- Nếu không có intervention: tiếp tục
- Output: State với `query_plan` (đã được user approve hoặc giữ nguyên)

**Node 1.5: Execute Search Graph**
- Gọi Graph 2 để thực thi các truy vấn trong `query_plan`
- Nhận về `search_results`
- Set `current_stage = "searching"`
- Output: State có `search_results`

**Node 1.6: Call Answer Generation Graph**
- Gọi Graph 3 với input là `user_query` + `search_results`
- Nhận về `final_answer`
- Set `current_stage = "answering"`
- Output: State có `final_answer`

**Node 1.7: Output Formatter**
- Format câu trả lời cuối cùng theo UI requirements
- Thêm metadata (sources, timestamps, confidence score)
- Set `current_stage = "completed"`
- Output: Formatted response

### Edges (Điều kiện chuyển node):

```
START 
  → Input Processor 
  → Routing Decision 
  → [Conditional]
      - If needs_research == False → Direct Answer (Node 1.7)
      - If needs_research == True → Call Query Planning Graph (Node 1.3)
  
Node 1.3 
  → User Intervention Checkpoint 
  → [Conditional]
      - If user_intervention exists → Wait for approval → Continue
      - Else → Execute Search Graph (Node 1.5)

Node 1.5 
  → Call Answer Generation Graph (Node 1.6)
  → Output Formatter (Node 1.7)
  → END
```

---

## GRAPH 2: QUERY PLANNING & EXECUTION GRAPH

**Mục đích:** Chuyên xử lý việc phân tích câu hỏi, tạo kế hoạch tìm kiếm, và thực thi tìm kiếm.

### State Schema:
```python
{
    "original_query": str,
    "query_analysis": dict,      # Kết quả phân tích câu hỏi
    "query_plan": list[dict],    # List các queries cần execute
    "execution_status": dict,    # Status của từng query
    "raw_results": list[dict],   # Kết quả thô từ search
    "processed_results": list[dict], # Kết quả đã xử lý
    "current_query_index": int
}
```

### Các Node:

**Node 2.1: Query Analyzer**
- Phân tích câu hỏi chi tiết:
  - Xác định intent (định nghĩa, so sánh, hướng dẫn, phân tích...)
  - Trích xuất entities chính
  - Xác định scope (rộng/hẹp)
  - Phát hiện ambiguity
  - Xác định temporal context (hiện tại/quá khứ/tương lai)
- Output: `query_analysis` với structure:
  ```python
  {
      "intent": str,
      "main_entities": list[str],
      "scope": str,
      "ambiguities": list[str],
      "temporal_context": str,
      "complexity_score": float
  }
  ```

**Node 2.2: Query Decomposer**
- Dựa vào `query_analysis`, phân rã câu hỏi thành các sub-queries
- Tạo strategy cho từng sub-query:
  - Query text
  - Search type (web/academic/documentation/news)
  - Priority (high/medium/low)
  - Dependencies (query này phụ thuộc query nào)
- Output: `query_plan` với structure:
  ```python
  [
      {
          "id": "q1",
          "query_text": "LangGraph là gì",
          "search_type": "documentation",
          "priority": "high",
          "dependencies": [],
          "status": "pending"
      },
      {
          "id": "q2",
          "query_text": "LangGraph architecture",
          "search_type": "documentation",
          "priority": "medium",
          "dependencies": ["q1"],
          "status": "pending"
      }
  ]
  ```

**Node 2.3: Query Validator**
- Kiểm tra tính hợp lệ của query_plan:
  - Có duplicate queries không?
  - Có queries quá vague không?
  - Có queries nào contradict nhau không?
  - Số lượng queries có hợp lý không? (tối đa 5-7)
- Nếu có vấn đề → gọi lại Node 2.2 với feedback
- Output: `query_plan` đã validated

**Node 2.4: Query Executor**
- Thực thi từng query trong plan theo thứ tự priority
- Với mỗi query:
  - Check dependencies đã complete chưa
  - Gọi search tool phù hợp (web_search/API)
  - Thu thập kết quả
  - Update `execution_status`
- Hỗ trợ parallel execution cho queries không có dependencies
- Output: `raw_results` và updated `execution_status`

**Node 2.5: Results Deduplicator**
- Loại bỏ duplicate content giữa các kết quả
- So sánh content similarity (dùng embeddings hoặc fuzzy matching)
- Loại bỏ low-quality sources (spam, ads, unreliable)
- Output: `raw_results` đã deduplicated

**Node 2.6: Results Processor**
- Xử lý từng result:
  - Extract main content
  - Identify key sentences/paragraphs
  - Tag với metadata (source, date, relevance score)
  - Chunk content thành sections có thể reference
- Rank results theo relevance với `original_query`
- Output: `processed_results` với structure:
  ```python
  [
      {
          "source_id": "src_1",
          "url": "https://...",
          "title": "...",
          "content_chunks": [
              {
                  "chunk_id": "src_1_c1",
                  "text": "...",
                  "relevance_score": 0.89
              }
          ],
          "overall_relevance": 0.85,
          "credibility_score": 0.92
      }
  ]
  ```

**Node 2.7: Results Evaluator**
- Đánh giá tổng thể:
  - Đủ thông tin để trả lời câu hỏi chưa?
  - Coverage: Có cover hết các aspects của câu hỏi không?
  - Quality: Nguồn có đáng tin cậy không?
- Nếu chưa đủ → generate additional queries → quay lại Node 2.4
- Nếu đủ → kết thúc
- Output: `search_complete: bool` và `processed_results`

### Edges:

```
START
  → Query Analyzer (Node 2.1)
  → Query Decomposer (Node 2.2)
  → Query Validator (Node 2.3)
  → [Conditional]
      - If validation_passed → Query Executor (Node 2.4)
      - Else → Loop back to Query Decomposer

Node 2.4
  → Results Deduplicator (Node 2.5)
  → Results Processor (Node 2.6)
  → Results Evaluator (Node 2.7)
  → [Conditional]
      - If search_complete == True → END (return processed_results)
      - Else → Generate additional queries → Node 2.4 (loop)
```

---

## GRAPH 3: ANSWER GENERATION GRAPH

**Mục đích:** Tổng hợp thông tin từ search results và tạo câu trả lời có trích dẫn chất lượng cao.

### State Schema:
```python
{
    "original_query": str,
    "search_results": list[dict],    # From Graph 2
    "content_analysis": dict,
    "answer_outline": dict,
    "draft_answer": str,
    "citations": list[dict],
    "final_answer": str,
    "quality_score": float
}
```

### Các Node:

**Node 3.1: Content Analyzer**
- Phân tích tất cả `search_results`:
  - Identify themes/topics
  - Detect consensus vs contradictions
  - Map content to query aspects
  - Identify gaps in information
- Output: `content_analysis` với structure:
  ```python
  {
      "main_themes": ["theme1", "theme2"],
      "consensus_points": ["point1", "point2"],
      "contradictions": [
          {
              "topic": "...",
              "source1_view": "...",
              "source2_view": "..."
          }
      ],
      "coverage_map": {
          "aspect1": ["src_1", "src_3"],
          "aspect2": ["src_2"]
      },
      "information_gaps": ["gap1", "gap2"]
  }
  ```

**Node 3.2: Answer Outliner**
- Dựa vào `content_analysis`, tạo outline cho câu trả lời:
  - Structure: Introduction → Main points → Conclusion
  - Với mỗi main point: liệt kê sources sẽ dùng
  - Quyết định flow logic
- Output: `answer_outline`

**Node 3.3: Draft Generator**
- Generate draft answer theo outline:
  - Viết từng section
  - Synthesize info từ multiple sources
  - Đảm bảo logical flow
  - Paraphrase content (KHÔNG copy nguyên văn)
- Đánh dấu positions cần citations: `[CITE: src_1_c3]`
- Output: `draft_answer`

**Node 3.4: Citation Mapper**
- Map mỗi claim trong draft với specific sources:
  - Identify factual claims
  - Link mỗi claim với chunk_id trong `search_results`
  - Create citation objects
- Output: `citations` với structure:
  ```python
  [
      {
          "claim_text": "LangGraph là framework để build stateful agents",
          "source_ids": ["src_1", "src_2"],
          "chunk_ids": ["src_1_c2", "src_2_c5"],
          "position_in_draft": 45
      }
  ]
  ```

**Node 3.5: Citation Formatter**
- Format citations theo style yêu cầu (ví dụ: inline, footnote, numbered)
- Insert citations vào draft_answer
- Đảm bảo mỗi factual claim đều có citation
- Remove các `[CITE: ...]` placeholders
- Output: `draft_answer` với citations formatted

**Node 3.6: Answer Refiner**
- Refine answer về:
  - Clarity: Dễ hiểu không?
  - Completeness: Trả lời đầy đủ câu hỏi không?
  - Coherence: Flow có mượt không?
  - Conciseness: Có verbose không?
- Adjust tone theo ngôn ngữ (formal/casual)
- Output: `final_answer`

**Node 3.7: Quality Evaluator**
- Đánh giá quality metrics:
  - Citation coverage (% claims có citations)
  - Source diversity (dùng bao nhiêu nguồn khác nhau)
  - Completeness (trả lời đủ aspects của query không)
  - Readability score
- Output: `quality_score` và optional improvement suggestions

**Node 3.8: Self-Critique (Optional)**
- LLM tự đánh giá answer:
  - Có factual errors không?
  - Có bias không?
  - Có missing important info không?
- Nếu quality_score < threshold → loop back to Node 3.6
- Output: `critique_passed: bool`

### Edges:

```
START
  → Content Analyzer (Node 3.1)
  → Answer Outliner (Node 3.2)
  → Draft Generator (Node 3.3)
  → Citation Mapper (Node 3.4)
  → Citation Formatter (Node 3.5)
  → Answer Refiner (Node 3.6)
  → Quality Evaluator (Node 3.7)
  → Self-Critique (Node 3.8)
  → [Conditional]
      - If critique_passed == True → END (return final_answer)
      - Else → Loop back to Answer Refiner (Node 3.6)
```

---

## 3. Communication Between Graphs

### Cách các Graph gọi nhau:

**Graph 1 → Graph 2:**
```python
# In Main Orchestrator
query_planning_result = await query_planning_graph.ainvoke({
    "original_query": state["user_query"]
})
state["query_plan"] = query_planning_result["query_plan"]
state["search_results"] = query_planning_result["processed_results"]
```

**Graph 1 → Graph 3:**
```python
# In Main Orchestrator
answer_result = await answer_generation_graph.ainvoke({
    "original_query": state["user_query"],
    "search_results": state["search_results"]
})
state["final_answer"] = answer_result["final_answer"]
state["citations"] = answer_result["citations"]
```

---

## 4. Hybrid Approach Implementation

### Cách implement "Automation by default, intervention on demand":

**Step 1: Default Flow (No Intervention)**
- Graph 1 gọi Graph 2 → nhận query_plan
- KHÔNG chờ user approval
- Ngay lập tức execute Graph 2 tiếp để search
- Stream results real-time về UI

**Step 2: Enable Intervention**
- Sau Node 1.3 (Call Query Planning Graph):
  - Emit `query_plan` về UI qua streaming
  - UI hiển thị plan với status "Executing..."
  - Tiếp tục execute mà KHÔNG chờ
  
- User có thể click "Pause & Edit" BẤT KỲ LÚC NÀO:
  - Graph 1 set `pause_requested = True`
  - Node 1.4 check flag này
  - Nếu True → dừng, chờ user edit
  - User submit edited plan → continue với updated plan

**Step 3: UI State Management**
```python
# Streaming updates về UI
{
    "type": "plan_created",
    "data": query_plan
}

{
    "type": "query_executing",
    "data": {
        "query_id": "q1",
        "status": "running"
    }
}

{
    "type": "query_completed",
    "data": {
        "query_id": "q1",
        "status": "completed",
        "results_count": 5
    }
}

{
    "type": "pause_checkpoint",
    "data": {
        "can_edit": True,
        "current_plan": query_plan
    }
}
```

---

## 5. Diagram Tổng Quan Flow

```
USER QUERY
    ↓
┌─────────────────────────────────────┐
│   GRAPH 1: MAIN ORCHESTRATOR        │
│                                     │
│  [Input] → [Router] → [Decision]   │
│                          ↓          │
│                    Needs Research?  │
│                     Yes ↓           │
└─────────────────────────┼───────────┘
                          ↓
┌─────────────────────────┼───────────┐
│   GRAPH 2: QUERY PLANNING           │
│                                     │
│  [Analyze] → [Decompose] → [Plan]  │
│      ↓                              │
│  [Execute] → [Process] → [Evaluate]│
│                                     │
│  Returns: processed_results         │
└─────────────────────────┼───────────┘
                          ↓
┌─────────────────────────┼───────────┐
│   GRAPH 1: (continued)              │
│                                     │
│  [User Intervention Checkpoint]     │
│       ↓  (if no pause)              │
│  [Execute Search] ← receives results│
│       ↓                             │
└───────────────────┬─────────────────┘
                    ↓
┌───────────────────┼─────────────────┐
│   GRAPH 3: ANSWER GENERATION        │
│                                     │
│  [Analyze] → [Outline] → [Draft]   │
│       ↓                             │
│  [Cite] → [Refine] → [Evaluate]    │
│                                     │
│  Returns: final_answer + citations  │
└───────────────────┼─────────────────┘
                    ↓
┌───────────────────┼─────────────────┐
│   GRAPH 1: (final)                  │
│                                     │
│  [Format Output] → [Return to User] │
└─────────────────────────────────────┘
```


## 7. Steps

1. **Start với Graph 2** (Query Planning): Đây là core logic
2. **Sau đó Graph 3** (Answer Generation): Logic tổng hợp
3. **Cuối cùng Graph 1** (Orchestrator): Kết nối tất cả

Với mỗi graph:
- Define State schema
- Implement từng node như functions
- Define edges với conditions
- Test riêng biệt từng graph
- Tích hợp vào Graph 1