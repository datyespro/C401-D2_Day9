# System Architecture — Lab Day 09

**Nhóm:** C401-D2
**Ngày:** 2026-04-14
**Version:** 1.0

---

## 1. Tổng quan kiến trúc

Hệ thống nhóm C401-D2 triển khai **Supervisor-Worker Multi-Agent Graph** bằng Python thuần (không dùng LangGraph library), với 3 workers chuyên biệt và 1 MCP server cung cấp external capability.

**Pattern đã chọn:** Supervisor-Worker

**Lý do chọn pattern này (thay vì single agent):**

Single agent RAG (Day 08) gộp toàn bộ logic retrieve → check policy → generate vào một pipeline — khi trả lời sai không rõ lỗi nằm ở retrieval, policy check hay generation. Supervisor-Worker tách biệt từng concern:
- Supervisor chỉ routing, không làm gì khác
- Mỗi worker có contract rõ (input/output), test độc lập được
- MCP server là abstraction layer cho external tools
- Trace ghi đủ `route_reason`, `worker_io_logs` → debug theo "Routing Error Tree"

---

## 2. Sơ đồ Pipeline

**Sơ đồ thực tế của nhóm:**

```
User Question (task)
        │
        ▼
┌────────────────────────────────────────┐
│           Supervisor Node              │
│  (graph.py — supervisor_node())        │
│                                        │
│  Keyword detection → 6 priority rules  │
│  Output: supervisor_route, route_reason│
│          risk_high, needs_tool         │
└──────────────────┬─────────────────────┘
                   │
          route_decision()
                   │
    ┌──────────────┼──────────────┐
    │              │              │
    ▼              ▼              ▼
[retrieval]  [policy_tool]  [human_review]
 worker       worker        (HITL node)
    │              │              │
    │    ┌─── retrieval ─────┘   │
    │    │    (always first)     │
    │    ▼                       │
    │  MCP Client                │
    │  ├── search_kb()           │
    │  ├── get_ticket_info()     │
    │  └── check_access()        │
    │    │                       │
    └────┼───────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│         Synthesis Worker               │
│  (workers/synthesis.py — run())        │
│                                        │
│  Input: retrieved_chunks + policy_result│
│  LLM: GPT-4o-mini (temp=0.1)          │
│  Output: final_answer, sources,        │
│          confidence (6-signal score)   │
└──────────────────┬─────────────────────┘
                   │
                   ▼
           AgentState final
    (final_answer, sources, confidence,
     route_reason, workers_called, trace)
```

**Key design decision:** Policy route LUÔN chạy `retrieval_worker` trước để synthesis có đủ chunk evidence từ cả hai nguồn.

---

## 3. Vai trò từng thành phần

### Supervisor (`graph.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Phân tích task, quyết định route sang worker nào, detect risk và multi-hop |
| **Input** | `task` (câu hỏi từ user) |
| **Output** | `supervisor_route`, `route_reason`, `risk_high`, `needs_tool` |
| **Routing logic** | Keyword signal detection — 6 nhóm theo thứ tự ưu tiên: policy_exception > access_control > refund_policy > sla_ticket > hr/it > default |
| **HITL condition** | Unknown error code pattern `ERR-\d{3}` không khớp với domain đã biết |

### Retrieval Worker (`workers/retrieval.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Embed query → query ChromaDB → trả về top-k chunks có score |
| **Embedding model** | SentenceTransformer `all-MiniLM-L6-v2` (offline, không cần API key) |
| **Top-k** | 3 (cấu hình qua `RETRIEVAL_TOP_K` trong .env) |
| **Stateless?** | Yes — không lưu state giữa các calls |

### Policy Tool Worker (`workers/policy_tool.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Kiểm tra exception cases và policy rules dựa trên retrieved chunks |
| **MCP tools gọi** | `search_kb`, `get_ticket_info`, `check_access_permission` (khi `needs_tool=True`) |
| **Exception cases xử lý** | `flash_sale_exception`, `digital_product_exception`, `emergency_access` |

### Synthesis Worker (`workers/synthesis.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **LLM model** | GPT-4o-mini (ưu tiên) / Gemini-1.5-flash (fallback) |
| **Temperature** | 0.1 — low để grounded, ít sáng tạo |
| **Grounding strategy** | System prompt: "CHỈ dùng context được cung cấp, KHÔNG dùng kiến thức ngoài" |
| **Abstain condition** | Khi `retrieved_chunks = []` hoặc answer chứa "không đủ thông tin" |
| **Confidence** | 6-signal heuristic: chunk score (70%) + quantity bonus + length factor − exception penalty |

### MCP Server (`mcp_server.py`)

| Tool | Input | Output |
|------|-------|--------|
| `search_kb` | `query: str`, `top_k: int = 3` | `{chunks, sources, total_found}` |
| `get_ticket_info` | `ticket_id: str` | ticket dict với SLA deadline, escalation info |
| `check_access_permission` | `access_level: int`, `requester_role: str`, `is_emergency: bool` | `{can_grant, required_approvers, emergency_override}` |
| `create_ticket` | `priority: str`, `title: str` | `{ticket_id, url, created_at}` (mock) |

**Deployment:** Mock Python class (standard, full credit) + FastAPI HTTP server tại port 8000 (bonus +2).

---

## 4. Shared State Schema (`AgentState`)

| Field | Type | Mô tả | Ai đọc/ghi |
|-------|------|-------|-----------| 
| `task` | str | Câu hỏi đầu vào từ user | Supervisor đọc |
| `supervisor_route` | str | Worker được chọn (`retrieval_worker`/`policy_tool_worker`/`human_review`) | Supervisor ghi, route_decision đọc |
| `route_reason` | str | Lý do route có format: `route=X \| signals: Y \| mcp_tools=Z` | Supervisor ghi |
| `risk_high` | bool | True khi phát hiện risk keyword (emergency, 2am...) | Supervisor ghi |
| `needs_tool` | bool | True khi cần gọi MCP | Supervisor ghi, policy_tool đọc |
| `hitl_triggered` | bool | True khi HITL node được gọi | human_review ghi |
| `retrieved_chunks` | list | `[{text, source, score, metadata}]` từ ChromaDB | retrieval ghi, policy_tool + synthesis đọc |
| `retrieved_sources` | list | Danh sách tên file nguồn | retrieval ghi |
| `policy_result` | dict | `{policy_applies, policy_name, exceptions_found}` | policy_tool ghi, synthesis đọc |
| `mcp_tools_used` | list | Log các MCP tool calls với timestamp | policy_tool ghi |
| `final_answer` | str | Câu trả lời cuối có citation | synthesis ghi |
| `sources` | list | Sources được cite trong answer | synthesis ghi |
| `confidence` | float | 0.0–1.0, tính từ 6 tín hiệu | synthesis ghi |
| `history` | list | Log từng bước qua các node | Tất cả ghi |
| `workers_called` | list | Danh sách worker đã được gọi theo thứ tự | Mỗi worker append |
| `worker_io_logs` | list | IO log chi tiết theo contract | Mỗi worker append |
| `latency_ms` | int | Tổng thời gian xử lý (ms) | graph ghi |
| `run_id` | str | ID unique của run (`run_YYYYMMDD_HHMMSS`) | graph ghi |

---

## 5. Lý do chọn Supervisor-Worker so với Single Agent (Day 08)

| Tiêu chí | Single Agent (Day 08) | Supervisor-Worker (Day 09) |
|----------|----------------------|--------------------------| 
| Debug khi sai | Khó — không rõ lỗi ở retrieval, policy check, hay generation | Dễ — xem `route_reason` + `worker_io_logs` trong trace |
| Thêm capability mới | Phải sửa toàn prompt | Thêm MCP tool + 1 routing rule |
| Routing visibility | Không có | Có `supervisor_route` + `route_reason` mỗi câu |
| Test từng phần | Không thể | Mỗi worker có `if __name__ == "__main__"` test độc lập |
| Thay worker | Phải refactor toàn pipeline | Swap 1 file, graph không đổi |

**Quan sát từ thực tế lab (từ `eval_report.json`):**

- Routing accuracy đạt **100%** (15/15) dù dùng keyword matching đơn giản, không LLM
- Debug time ước tính giảm từ ~15 phút/bug (Day 08) xuống ~3–5 phút/bug (Day 09) nhờ trace rõ ràng
- Overhead latency thực tế: ~5,350ms/query (multi-step) — đáng chú ý so với single-step RAG

---

## 6. Giới hạn và điểm cần cải tiến

1. **ChromaDB index chưa hoàn chỉnh:** `retrieval_worker` hay trả về `chunks=[]` → synthesis phải abstain → `avg_confidence = 0.139` thấp bất thường. Cần build proper index với chunking strategy và metadata đầy đủ.

2. **Keyword routing không scale:** Pattern matching sẽ fail với câu hỏi diễn đạt theo cách không ngờ tới. Long-term cần upgrade sang LLM-based intent classifier hoặc embedding-based routing.

3. **Confidence score là heuristic:** `_estimate_confidence()` dùng 6 tín hiệu nhưng chưa được calibrate. Cần LLM-as-Judge hoặc human evaluation để validate.
