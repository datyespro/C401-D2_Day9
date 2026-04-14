# Báo Cáo Nhóm — Lab Day 09: Multi-Agent Orchestration

**Tên nhóm:** C401-D2
**Thành viên:**

| Tên | Vai trò | Sprint lead |
|-----|---------|-------------|
| Nguyễn Thành Đạt | Supervisor Owner | Sprint 1 |
| Hoàng Ngọc Anh | Retrieval Worker Owner | Sprint 2 |
| Nguyễn Hoàng Việt | Policy Tool Worker Owner | Sprint 2 |
| Vũ Duy Linh | MCP System Owner | Sprint 3 |
| Đậu Văn Quyền | Evaluate & Trace Owner | Sprint 4 |
| Nguyễn Anh Đức | Documentation & Synthesis Owner | Sprint 2 + 4 |

**Ngày nộp:** 2026-04-14
**Repo:** [URL GitHub của nhóm]
**Độ dài:** ~800 từ

---

## 1. Kiến trúc nhóm đã xây dựng

Nhóm xây dựng hệ thống **Supervisor-Worker Multi-Agent Graph** bằng Python thuần (không dùng LangGraph library). Kiến trúc gồm 4 thành phần chính:

**Pipeline flow:**
```
User Question
      │
      ▼
┌─────────────────┐
│   Supervisor    │  ← keyword detection, risk_high, needs_tool
│  (graph.py)     │
└──────┬──────────┘
       │ route_decision()
  ┌────┴──────────────────────────────┐
  │                                   │
  ▼                                   ▼
retrieval_worker              policy_tool_worker
(retrieval.py)                 (policy_tool.py)
  │                     ┌──── gọi MCP tools ────┐
  │                     │    search_kb()         │
  │                     │    get_ticket_info()   │
  │                     └───────────────────────┘
  └──────────────────┬────────────────┘
                     ▼
             synthesis_worker
              (synthesis.py)
                     │
                     ▼
              final_answer
          + sources + confidence
```

**Routing logic cốt lõi:**

Supervisor dùng **keyword signal detection** (deterministic, không gọi LLM) với 6 nhóm keyword theo thứ tự ưu tiên:
1. `policy_exception` (flash sale, license key...) → `policy_tool_worker`
2. `access_control` (cấp quyền, level 2/3...) → `policy_tool_worker`
3. `refund_policy` + decision signal → `policy_tool_worker`
4. `sla_ticket` (P1, ticket, escalation...) → `retrieval_worker`
5. `hr/it_helpdesk` → `retrieval_worker`
6. `unknown_error_code` (ERR-\d{3}) → `human_review`

Multi-hop queries (span ≥ 2 domains) được ưu tiên route về `policy_tool_worker` vì worker này xử lý cross-document reasoning tốt hơn.

**MCP tools đã tích hợp (`mcp_server.py` — 4 tools, mock class + HTTP server FastAPI):**
- `search_kb(query, top_k)` — delegate ChromaDB retrieval, trả về chunks + sources
- `get_ticket_info(ticket_id)` — tra cứu mock ticket database (P1-LATEST, IT-1234)
- `check_access_permission(level, role, emergency)` — kiểm tra điều kiện cấp quyền theo access_control_sop.txt
- `create_ticket(priority, title)` — tạo ticket mock

Ví dụ trace gọi MCP (`run_20260414_164000.json`):
```json
"mcp_tools_used": [
  {"tool": "search_kb", "input": {"query": "Ticket P1 luc 2am...", "top_k": 3}},
  {"tool": "get_ticket_info", "input": {"ticket_id": "P1-LATEST"}}
]
```

---

## 2. Quyết định kỹ thuật quan trọng nhất

**Quyết định:** Policy route LUÔN chạy `retrieval_worker` trước, sau đó mới chạy `policy_tool_worker`.

**Bối cảnh vấn đề:**

Khi thiết kế routing, nhóm đối mặt với câu hỏi: với câu hỏi policy (Flash Sale, Access Control), có cần retrieve evidence trước không? Nếu policy_tool_worker có thể trả lời hoàn toàn từ rule-based logic và MCP, thì skip retrieval sẽ nhanh hơn.

**Các phương án đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|------------|
| Policy không cần retrieval | Nhanh hơn (~1s) | Policy worker không có chunk context → synthesis dùng ít evidence hơn |
| **Policy luôn retrieve trước** | Synthesis có tối đa evidence từ cả hai nguồn | Thêm 1 bước retrieval, tăng latency |
| Supervisor quyết định case-by-case | Linh hoạt nhất | Logic phức tạp hơn, khó debug |

**Phương án đã chọn và lý do:**

Policy route LUÔN retrieve trước (dòng 429–434 trong `graph.py`):
```python
elif route == "policy_tool_worker":
    # ALWAYS retrieve evidence first, then run policy analysis
    state = retrieval_worker_node(state)   # ← retrieve trước
    state = policy_tool_worker_node(state) # ← policy sau
```

Lý do: Synthesis worker cần `retrieved_chunks` để tổng hợp answer có citation. Nếu policy_tool_worker chạy trước mà retrieval chưa có kết quả, synthesis chỉ có `policy_result` — answer thiếu evidence document. Đây là trade-off latency (+~200ms) đổi lấy answer quality tốt hơn.

**Bằng chứng từ trace:**
```
run_20260414_163907.json — Flash Sale query:
  workers_called: ["retrieval_worker", "policy_tool_worker", "synthesis_worker"]
  final_answer: "Khách hàng Flash Sale... không được hoàn tiền. [chính sách v4]"
```

---

## 3. Kết quả grading questions

> *(Mục này sẽ được cập nhật sau 17:00 khi `grading_questions.json` được public)*

**Từ kết quả `eval_report.json` (15 test questions):**

| Metric | Giá trị |
|--------|---------|
| Routing accuracy | **100%** (15/15 câu route đúng) |
| Source hit rate | **100%** (14/14 câu có nguồn đúng) |
| Avg confidence | 0.139 (thấp vì ChromaDB chưa index đầy đủ) |
| Avg latency | ~5,350ms |
| MCP usage rate | 21% (18/84 calls) |
| HITL triggered | 7% (6/84 — câu có unknown error code) |

**Câu pipeline xử lý tốt nhất:**
- Flash Sale exception query → `policy_tool_worker` detect đúng `flash_sale_exception`, synthesis trả lời có citation `[chính sách v4]`

**Câu pipeline gặp khó khăn:**
- Câu về "mức phạt tài chính SLA P1" → retrieval không tìm được evidence → synthesis abstain đúng, nhưng confidence vẫn là 0.1 — khó phân biệt với câu fail thực sự

**Câu gq07 (abstain):** Pipeline xử lý đúng cơ chế — khi `retrieved_chunks = []`, synthesis_worker trả về "Không đủ thông tin trong tài liệu nội bộ." thay vì hallucinate. `confidence=0.1` (< threshold) cho phép trace owner nhận diện câu này là abstain case.

**Câu gq09 (multi-hop khó nhất):** Trace ghi đúng 2 workers được gọi: `["retrieval_worker", "policy_tool_worker", "synthesis_worker"]`. Supervisor detect được `multi_hop=True` từ signal `access_control[level 2]` + `sla_ticket[p1]`.

---

## 4. So sánh Day 08 vs Day 09 — Điều nhóm quan sát được

**Metric thay đổi rõ nhất (có số liệu từ `eval_report.json`):**

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) |
|--------|----------------------|---------------------|
| Routing visibility | ✗ Không có | ✓ `route_reason` trong mọi trace |
| Worker testability | ✗ Không thể | ✓ Test từng worker độc lập |
| MCP support | ✗ Không có | ✓ 4 tools, 21% usage rate |
| Debug time (ước tính) | ~15 phút/bug | ~3–5 phút/bug |
| Routing accuracy | N/A | 100% (15/15) |
| Avg latency | N/A (baseline) | ~5,350ms |

**Điều nhóm bất ngờ nhất:**

Routing logic đơn giản (keyword matching, không dùng LLM) lại đạt 100% routing accuracy trên 15 test questions — và nhanh hơn đáng kể (~5ms/routing decision so với ~800ms nếu dùng LLM classifier). Điều này cho thấy với bộ câu hỏi có pattern rõ, deterministic routing đủ tốt và dễ debug hơn nhiều.

**Trường hợp multi-agent KHÔNG giúp ích:**

Simple single-document queries (e.g. "Mật khẩu đổi mấy ngày?") — multi-agent tạo overhead gọi thêm supervisor + synthesis không cần thiết, trong khi single-agent RAG có thể trả lời trong 1 step. Latency tăng ~3–5x so với Day 08 cho các câu đơn giản này.

---

## 5. Phân công và đánh giá nhóm

**Phân công thực tế:**

| Thành viên | Phần đã làm | Sprint |
|------------|-------------|--------|
| Nguyễn Thành Đạt | `graph.py` — AgentState, supervisor_node, route_decision, HITL | S1 |
| Hoàng Ngọc Anh | `workers/retrieval.py` — ChromaDB query, dense retrieval | S2 |
| Nguyễn Hoàng Việt | `workers/policy_tool.py` — rule-based policy check, exception detection | S2 |
| Vũ Duy Linh | `mcp_server.py` — 4 tools, FastAPI HTTP server (bonus) | S3 |
| Đậu Văn Quyền | `eval_trace.py` — 15 test questions, eval_report.json, grading log | S4 |
| Nguyễn Anh Đức | `workers/synthesis.py`, `docs/`, `reports/group_report.md` | S2+4 |

**Điều nhóm làm tốt:**

- Tách vai rõ ràng từ phút đầu → gần như không có merge conflict
- graph.py thiết kế fallback placeholder cho mỗi worker → team có thể test từng phần độc lập trước khi integrate
- MCP server có cả mock class lẫn FastAPI HTTP server (đạt bonus +2)

**Điều nhóm làm chưa tốt:**

- ChromaDB index chưa được build với full metadata → `retrieval_worker` trả về `chunks=[]` trong nhiều trace → synthesis hay phải abstain → confidence toàn bộ thấp
- Cần đồng bộ format của `retrieved_chunks` sớm hơn — M3 và synthesis worker có kết nối qua `policy_result` nhưng format ban đầu chưa khớp contract hoàn toàn

**Nếu làm lại, nhóm sẽ thay đổi gì:**

Dành 15 phút đầu build ChromaDB index chung và verify `retrieval_worker` trả về chunks thật trước khi các worker khác bắt đầu code. Điều này tránh pattern "works in test with mock data, fails in integration".

---

## 6. Nếu có thêm 1 ngày, nhóm sẽ làm gì?

**Cải tiến 1:** Build ChromaDB index với chunking tốt hơn (overlapping chunks, metadata đầy đủ) để `retrieval_worker` trả về evidence thực sự. Lý do: `eval_report.json` cho thấy `avg_confidence=0.139` thấp bất thường — không phải synthesis kém mà do retrieval trả về empty chunks, buộc synthesis phải abstain.

**Cải tiến 2:** Upgrade `_estimate_confidence()` trong synthesis thành LLM-as-Judge để phân biệt "không có context" (retrieval fail) với "context không đủ để trả lời" (semantic gap) — hai trường hợp có chiến lược xử lý khác nhau trong production system.

---

*File lưu tại: `reports/group_report.md`*
*Commit sau 18:00 được phép theo SCORING.md*
