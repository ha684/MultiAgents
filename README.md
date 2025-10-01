Mô tả các Node (Agent)
Bước 1 & 2: User Query & Router
Mục đích: Phân loại câu hỏi của người dùng để quyết định có cần vào flow nghiên cứu phức tạp hay không.
Đầu vào: state['original_query']
Logic: Dùng một LLM nhỏ (như Haiku) với prompt đơn giản để phân loại query thành "simple_chitchat" hoặc "needs_research".
Đầu ra: Quyết định điều hướng (chitchat hoặc research). Nếu là chitchat, trả lời trực tiếp. Nếu là research, chuyển tới Query Planner.
Bước 3: Query Planner
Mục đích: Phân rã câu hỏi phức tạp thành một kế hoạch gồm nhiều câu hỏi con có độ ưu tiên.
Đầu vào: state['original_query']
Logic: Sử dụng một LLM tốt (như Sonnet) với prompt đã được cung cấp để tạo ra cấu trúc JSON gồm core_queries và optional_queries. Đây là một bước cực kỳ quan trọng, quyết định "lộ trình" ban đầu.
Đầu ra: Cập nhật state['search_plan'] và state['pending_queries'].
Bước 4: Search Executor
Mục đích: Lấy một query từ danh sách chờ và thực thi tìm kiếm (web search, RAG, v.v.).
Đầu vào: Lấy query đầu tiên từ state['pending_queries'].
Logic: Gọi API của công cụ tìm kiếm (Tavily, Serper...) hoặc cơ sở dữ liệu vector.
Đầu ra: Cập nhật state['search_results'] với danh sách các tài liệu/snippets tìm được.
Bước 5: Reranker
Mục đích: Sắp xếp lại các kết quả tìm kiếm thô để đưa những thông tin liên quan nhất lên đầu.
Đầu vào: state['search_results'], state['original_query'] (hoặc sub-query hiện tại).
Logic: Sử dụng một mô hình reranker chuyên dụng (như Cohere Rerank) hoặc một LLM nhỏ để chấm điểm mức độ liên quan của từng tài liệu. Giữ lại top 3-5 kết quả tốt nhất.
Đầu ra: Cập nhật state['search_results'] với danh sách đã được sắp xếp và lọc.
Bước 6: Compressor
Mục đích: Trích xuất những thông tin cốt lõi nhất từ các tài liệu top-ranked để giảm token và nhiễu.
Đầu vào: state['search_results'] (đã rerank).
Logic: Với mỗi tài liệu, dùng một LLM nhỏ (như Haiku) để tóm tắt hoặc trích xuất các câu/đoạn trả lời trực tiếp cho câu hỏi con.
Đầu ra: Một chuỗi văn bản (string) chứa thông tin đã được chắt lọc.
Bước 7: Knowledge Merger
Mục đích: Hợp nhất thông tin mới tìm được vào "bộ não" chung của hệ thống.
Đầu vào: Thông tin đã nén từ Compressor, state['accumulated_knowledge'].
Logic: Đây có thể là một bước đơn giản như nối chuỗi, nhưng để tối ưu hơn, bạn có thể dùng LLM để viết lại accumulated_knowledge sao cho mạch lạc, loại bỏ thông tin trùng lặp và thêm vào thông tin mới.
Đầu ra: Cập nhật state['accumulated_knowledge'] với phiên bản mới.
Bước 8: Verification Agent (Nhạc trưởng của vòng lặp)
Mục đích: Đánh giá xem thông tin đã đủ để trả lời câu hỏi gốc chưa và quyết định hành động tiếp theo.
Đầu vào: state['accumulated_knowledge'], state['original_query'], state['pending_queries'], state['iteration_count'].
Logic: Dùng một LLM khá (như Sonnet) với prompt chi tiết như đã thiết kế. LLM sẽ trả về một JSON chứa sufficient, confidence, next_action, và missing_aspects.
Đầu ra: Quyết định điều hướng: continue_planned, generate_dynamic, hoặc synthesize.
Bước 9: Dynamic Query Generator (Lưới an toàn)
Mục đích: Tạo ra các câu hỏi tìm kiếm mới để lấp đầy những lỗ hổng thông tin mà Verification Agent đã chỉ ra.
Đầu vào: state['verification']['missing_aspects'], state['accumulated_knowledge'], state['original_query'].
Logic: Chỉ được gọi khi các query trong kế hoạch ban đầu đã hết nhưng thông tin vẫn chưa đủ. Dùng LLM (Sonnet) để tạo 1-2 query mới, rất cụ thể.
Đầu ra: Thêm các query mới này vào state['pending_queries'] để vòng lặp nghiên cứu tiếp tục.
Logic điều hướng (The Edges)
Sau khi Verification Agent chạy, bạn cần một hàm để đọc kết quả và quyết định node tiếp theo:
code
Python
def route_after_verification(state):
    action = state['verification']['next_action']
    
    if state['iteration_count'] >= state['max_searches']:
        return "fact_checker" # Bắt buộc dừng
    
    if action == "synthesize":
        return "fact_checker"
    elif action == "continue_planned":
        if not state['pending_queries']: # Nếu không còn query nào thì chuyển sang dynamic
            return "dynamic_query_generator"
        return "search_executor"
    elif action == "generate_dynamic":
        return "dynamic_query_generator"
Giai đoạn cuối
Bước 10: Fact Checker
Mục đích: Kiểm tra lần cuối toàn bộ thông tin đã thu thập, tìm kiếm mâu thuẫn hoặc các "ảo giác" (hallucinations) tiềm tàng.
Đầu vào: state['accumulated_knowledge'].
Logic: Dùng một LLM mạnh (Sonnet) với prompt yêu cầu nó đóng vai một người biên tập viên khó tính. Yêu cầu nó xác định các tuyên bố (claims), đánh dấu những điểm không nhất quán hoặc thiếu nguồn tin cậy.
Đầu ra: Một phiên bản "sạch" hơn của accumulated_knowledge, có thể kèm theo các ghi chú cảnh báo.
Bước 11: Final Synthesizer
Mục đích: Soạn thảo câu trả lời cuối cùng cho người dùng một cách tự nhiên, mạch lạc và đầy đủ.
Đầu vào: state['accumulated_knowledge'] (đã qua Fact Checker), state['original_query'].
Logic: Sử dụng mô hình LLM mạnh nhất bạn có (như Opus) để tạo ra câu trả lời cuối cùng. Prompt nên yêu cầu nó trả lời dựa CHỈ vào thông tin được cung cấp, trích dẫn nguồn nếu có, và trình bày theo một định dạng dễ đọc.
Đầu ra: Câu trả lời cuối cùng để hiển thị cho người dùng.

Kiến trúc Tổng thể: 2 Graph Chính
Để hệ thống rõ ràng, dễ bảo trì và mở rộng, chúng ta không nên tạo một Graph khổng lồ với 11 bước. Thay vào đó, chúng ta sẽ thiết kế theo kiến trúc Orchestrator - Subgraph:
Orchestrator Graph (Graph Điều Phối): Graph chính, cấp cao nhất. Nhiệm vụ của nó là điều phối luồng công việc chung: nhận yêu cầu, quyết định có cần nghiên cứu không, gọi subgraph nghiên cứu, kiểm tra lại kết quả và tổng hợp câu trả lời cuối cùng.
Research Graph (Graph Nghiên cứu - Subgraph): Một graph con chuyên dụng, thực hiện vòng lặp tìm kiếm thông tin. Nó nhận một kế hoạch và tự vận hành cho đến khi thu thập đủ thông tin, sau đó trả kết quả về cho Orchestrator.
Lợi ích của cách tiếp cận này:
Rõ ràng: Tách biệt rõ ràng giữa logic điều phối cấp cao và logic lặp đi lặp lại của việc nghiên cứu.
Tái sử dụng: Bạn có thể dễ dàng tái sử dụng Research Graph ở những nơi khác.
Dễ gỡ lỗi (Debug): Bạn có thể chạy và kiểm tra riêng Research Graph mà không cần chạy toàn bộ hệ thống.
code
Mermaid
graph TD
    subgraph "Orchestrator Graph"
        A[1. User Query] --> B{2. Router}
        B --> |Chitchat| K[11. Final Synthesizer]
        B --> |Research| C(Invoke Research Graph)
        C --> D[10. Fact Checker]
        D --> K
        K --> L[Response]
    end

    subgraph "Research Graph (Subgraph)"
        S_A[3. Query Planner] --> S_B[4. Search Executor]
        S_B --> S_C[5, 6, 7. Process Results]
        S_C --> S_D{8. Verification Agent}
        S_D -- "Continue Planned" --> S_B
        S_D -- "Generate Dynamic" --> S_E[9. Dynamic Query Generator]
        S_E --> S_B
        S_D -- "Sufficient" --> S_F((End & Return))
    end

    C -- Calls --> S_A
    S_F -- Returns 'accumulated_knowledge' --> C
Định nghĩa State Object (Trái tim của Graph)
Toàn bộ hệ thống sẽ hoạt động dựa trên một đối tượng State duy nhất. Trong LangGraph, chúng ta sẽ định nghĩa nó bằng TypedDict.
code
Python
from typing import List, TypedDict, Dict, Optional

class SearchPlan(TypedDict):
    core_queries: List[Dict]
    optional_queries: List[Dict]
    max_searches: int

class VerificationResult(TypedDict):
    sufficient: bool
    confidence: float
    next_action: str # "continue_planned" | "generate_dynamic" | "synthesize"
    missing_aspects: List[str]

class AgentState(TypedDict):
    original_query: str
    is_chitchat: bool
    
    # State for Research Subgraph
    search_plan: SearchPlan
    pending_queries: List[Dict]
    completed_queries: List[Dict]
    accumulated_knowledge: str
    search_results: List[Dict] # Raw results from the latest search
    iteration_count: int
    
    # State for final synthesis
    verification_result: VerificationResult
    final_answer: str
Mô Tả Chi Tiết Từng Bước và Node trong Graph
Phần 1: Orchestrator Graph (Graph Điều Phối)
Graph này có 4 node chính và các cạnh điều hướng.
Node 1: router
Bước tương ứng: 2. Router
Mục đích: Phân loại câu hỏi của người dùng.
Đầu vào: state['original_query']
Logic thực thi:
Gọi một LLM nhỏ (ví dụ: Claude Haiku) với prompt để phân loại câu hỏi thành "chitchat" (trò chuyện đơn giản) hoặc "research" (cần nghiên cứu sâu).
Prompt ví dụ: "Phân loại câu hỏi sau: '{original_query}'. Trả về 'chitchat' nếu đây là lời chào hỏi hoặc câu hỏi đơn giản không cần tìm kiếm. Ngược lại, trả về 'research'."
Đầu ra: Cập nhật state['is_chitchat'] (True/False).
Cạnh điều hướng (Conditional Edge) sau router:
Tên: should_research
Logic:
Nếu state['is_chitchat'] là True, đi đến node final_synthesizer để trả lời trực tiếp.
Nếu state['is_chitchat'] là False, đi đến node research_subgraph.
Node 2: research_subgraph
Bước tương ứng: 3, 4, 5, 6, 7, 8, 9 (Toàn bộ vòng lặp nghiên cứu)
Mục đích: Invocation (gọi) toàn bộ Research Graph như một bước duy nhất.
Đầu vào: state (chỉ các trường cần thiết như original_query).
Logic thực thi:
Khởi tạo Research Graph.
Gọi phương thức invoke() của Research Graph với state hiện tại.
Research Graph sẽ tự chạy vòng lặp bên trong nó.
Khi Research Graph kết thúc, nó sẽ trả về một state đã được cập nhật.
Đầu ra: Cập nhật state với kết quả từ Research Graph, quan trọng nhất là state['accumulated_knowledge'].
Node 3: fact_checker
Bước tương ứng: 10. Fact Checker
Mục đích: Rà soát lại toàn bộ thông tin đã thu thập để tìm mâu thuẫn và đảm bảo tính nhất quán.
Đầu vào: state['accumulated_knowledge'], state['original_query'].
Logic thực thi:
Gọi một LLM mạnh (ví dụ: Claude Sonnet) với prompt yêu cầu nó đóng vai một người kiểm duyệt viên.
Prompt ví dụ: "Dựa trên câu hỏi gốc '{original_query}', hãy đọc kỹ khối kiến thức sau: '{accumulated_knowledge}'. Xác định bất kỳ tuyên bố nào có vẻ mâu thuẫn, không đáng tin cậy hoặc có thể là ảo giác. Viết lại khối kiến thức này, loại bỏ hoặc gắn cờ các điểm đáng ngờ."
Đầu ra: Cập nhật state['accumulated_knowledge'] với phiên bản đã được kiểm duyệt.
Node 4: final_synthesizer
Bước tương ứng: 11. Final Synthesizer
Mục đích: Soạn thảo câu trả lời cuối cùng cho người dùng.
Đầu vào:
Nếu từ router (chitchat): state['original_query'].
Nếu từ fact_checker: state['accumulated_knowledge'], state['original_query'].
Logic thực thi:
Gọi LLM mạnh nhất (ví dụ: Claude Opus).
Nếu là chitchat, chỉ cần trả lời câu hỏi.
Nếu là research, dùng prompt: "Dựa CHỈ vào khối kiến thức được cung cấp sau đây, hãy viết một câu trả lời toàn diện, có cấu trúc tốt cho câu hỏi gốc. Câu hỏi gốc: '{original_query}'. Kiến thức: '{accumulated_knowledge}'."
Đầu ra: Cập nhật state['final_answer']. Đây là kết quả cuối cùng.
Phần 2: Research Graph (Subgraph)
Graph này chứa vòng lặp nghiên cứu cốt lõi. Nó có 5 node và các cạnh điều hướng phức tạp hơn.
Node A: query_planner (Điểm bắt đầu của subgraph)
Bước tương ứng: 3. Query Planner
Mục đích: Tạo kế hoạch tìm kiếm ban đầu.
Đầu vào: state['original_query']
Logic thực thi: Gọi LLM (Sonnet) với prompt chi tiết để tạo ra cấu trúc JSON gồm core_queries, optional_queries, và max_searches.
Đầu ra: Cập nhật state['search_plan'], state['pending_queries'], state['max_searches'].
Node B: search_executor
Bước tương ứng: 4. Search Executor
Mục đích: Thực thi một truy vấn tìm kiếm.
Đầu vào: state['pending_queries'].
Logic thực thi:
Lấy truy vấn đầu tiên từ state['pending_queries'].
Gọi công cụ tìm kiếm (web search, RAG...).
Di chuyển truy vấn từ pending_queries sang completed_queries.
Tăng state['iteration_count'].
Đầu ra: Cập nhật state['search_results'] với kết quả thô, state['completed_queries'], state['pending_queries'], state['iteration_count'].
Node C: process_results
Bước tương ứng: 5 (Reranker), 6 (Compressor), 7 (Knowledge Merger). Gộp 3 bước này vào một node cho gọn.
Mục đích: Tinh chỉnh và tích hợp thông tin mới.
Đầu vào: state['search_results'], state['accumulated_knowledge'].
Logic thực thi:
Rerank: Sắp xếp state['search_results'] theo mức độ liên quan.
Compress: Tóm tắt top 3-5 kết quả liên quan nhất thành một đoạn văn bản ngắn gọn.
Merge: Nối hoặc tích hợp đoạn văn bản đã tóm tắt vào state['accumulated_knowledge'].
Đầu ra: Cập nhật state['accumulated_knowledge'] với thông tin mới.
Node D: verification_agent
Bước tương ứng: 8. Verification Agent
Mục đích: Quyết định hành động tiếp theo của vòng lặp.
Đầu vào: state['accumulated_knowledge'], state['original_query'], state['pending_queries'], state['iteration_count'].
Logic thực thi: Gọi LLM (Sonnet) với prompt đánh giá mức độ đầy đủ thông tin để tạo ra JSON chứa sufficient, next_action, missing_aspects.
Đầu ra: Cập nhật state['verification_result'].
Cạnh điều hướng (Conditional Edge) sau verification_agent:
Tên: route_research_loop
Logic:
Nếu state['iteration_count'] >= state['max_searches'] -> __end__ (Kết thúc subgraph).
Đọc action = state['verification_result']['next_action'].
Nếu action == "synthesize" -> __end__ (Kết thúc subgraph).
Nếu action == "continue_planned" VÀ state['pending_queries'] còn -> Đi đến node search_executor.
Nếu action == "continue_planned" VÀ state['pending_queries'] đã hết -> Đi đến node dynamic_query_generator (phòng trường hợp kế hoạch ban đầu không đủ).
Nếu action == "generate_dynamic" -> Đi đến node dynamic_query_generator.
Node E: dynamic_query_generator
Bước tương ứng: 9. Dynamic Query Generator
Mục đích: Tạo truy vấn mới dựa trên lỗ hổng thông tin.
Đầu vào: state['verification_result']['missing_aspects'], state['accumulated_knowledge'].
Logic thực thi: Gọi LLM (Sonnet) để tạo 1-2 truy vấn mới nhắm vào các missing_aspects.
Đầu ra: Thêm các truy vấn mới vào state['pending_queries']. Node này sẽ luôn đi tiếp tới search_executor.