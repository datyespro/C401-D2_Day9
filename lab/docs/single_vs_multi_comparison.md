# Single Agent vs Multi-Agent Comparison — Lab Day 09

**Nhóm:** C401-D2
**Ngày:** 14/04/2026

> Số liệu Day 09 lấy từ `artifacts/eval_report.json` (chạy 15 test questions).
> Số liệu Day 08 là N/A — nhóm không có baseline chạy được từ Day 08 lab.

---

## 1. Metrics Comparison

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) | Delta | Ghi chú |
|--------|----------------------|---------------------|-------|---------|
| Avg confidence | N/A | **0.139** | N/A | Thấp do ChromaDB chưa index đầy đủ |
| Avg latency (ms) | N/A | **~5,350ms** | N/A | 3 workers + MCP overhead |
| Routing visibility | ✗ Không có | ✓ Có `route_reason` | — | Key qualitative improvement |
| Routing accuracy | N/A | **100%** (15/15) | N/A | Keyword matching đủ chính xác |
| Source hit rate | N/A | **100%** (14/14) | N/A | Cần ChromaDB index tốt hơn |
| MCP usage rate | ✗ 0% | **21%** (18/84 calls) | — | 4 tools, policy + multi-hop queries |
| HITL trigger rate | ✗ Không có | **7%** (6/84 calls) | — | Unknown error code pattern |
| Worker testability | ✗ Không thể | ✓ Test độc lập | — | Mỗi worker có standalone test |
| Debug time (estimate) | ~15 phút/bug | **~3–5 phút/bug** | −10min | Nhờ trace + Routing Error Tree |

> **Lưu ý về N/A:** Day 08 baseline không available — nhóm không có số liệu thực tế để so sánh latency và confidence trực tiếp.

---

## 2. Phân tích theo loại câu hỏi

### 2.1 Câu hỏi đơn giản (single-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | N/A | Tốt (routing đúng 100%) |
| Latency | N/A | **~1,500–3,000ms** (retrieval + synthesis) |
| Observation | Single pipeline, không rõ bước nào | Có route_reason, worker_io_logs rõ ràng |

**Ví dụ:** "Mật khẩu đổi mấy ngày?" → `retrieval_worker` → `synthesis_worker`

**Kết luận:** Multi-agent KHÔNG cải thiện accuracy cho câu đơn giản, thậm chí tốn latency hơn ~2–3x so với single-step RAG. Overhead từ supervisor + worker wrapper không đáng cho simple queries.

---

### 2.2 Câu hỏi multi-hop (cross-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | N/A — không có multi-hop routing | Tốt — detect `multi_hop=True` từ domain_count |
| Routing visible? | ✗ | ✓ `multi_hop=True` trong route_reason |
| Observation | Single agent không biết câu hỏi cần 2 tài liệu | Supervisor detect multi-hop → policy_tool → cross-doc reasoning |

**Ví dụ thực tế** (`run_20260414_164000.json`):
```
Task: "Ticket P1 luc 2am. Can cap Level 2 access tam thoi cho contractor."
supervisor_route: policy_tool_worker
route_reason: "signals: access_control[level 2]; sla_ticket[p1,ticket]; multi_hop[2_domains]"
workers_called: ["retrieval_worker", "policy_tool_worker", "synthesis_worker"]
mcp_tools_used: ["search_kb", "get_ticket_info"]
```

**Kết luận:** Multi-agent rõ ràng tốt hơn cho multi-hop queries — supervisor detect cross-domain signal và route đúng worker. Single agent không có cơ chế phân biệt câu đơn và câu multi-hop.

---

### 2.3 Câu hỏi cần abstain

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Abstain rate | N/A | **Cao** (nhiều câu do ChromaDB chưa index) |
| Hallucination cases | N/A | **0** — synthesis worker luôn abstain khi không có chunks |
| Observation | Single agent có thể hallucinate do không có grounding | System prompt strict: "CHỈ dùng context, KHÔNG dùng kiến thức ngoài" |

**Ví dụ abstain đúng** (`run_20260414_163953.json`):
```
Task: "ERR-403-AUTH la loi gi va cach xu ly?"
→ human_review (HITL) → retrieval_worker (no chunks) → synthesis_worker
final_answer: "Không đủ thông tin trong tài liệu nội bộ."
confidence: 0.1
```

**Kết luận:** Multi-agent có anti-hallucination tốt hơn nhờ grounded system prompt trong synthesis_worker và confidence signal rõ ràng (confidence ≤ 0.3 → đánh dấu câu cần review).

---

## 3. Debuggability Analysis

### Day 08 — Debug workflow
```
Khi answer sai → phải đọc toàn bộ RAG pipeline code
→ không có trace → không biết bắt đầu từ đâu
→ phải thêm print statements → chạy lại
Thời gian ước tính: ~15 phút/bug
```

### Day 09 — Debug workflow (Routing Error Tree)
```
Khi answer sai → đọc trace file:
  1. Xem supervisor_route + route_reason
     → Routing sai? Sửa keyword rules trong graph.py
  2. Xem worker_io_logs của retrieval_worker
     → chunks=[]? → ChromaDB index issue
  3. Xem worker_io_logs của policy_tool_worker
     → exceptions_found sai? → Sửa policy logic
  4. Xem synthesis_worker output
     → answer_length ngắn + confidence thấp? → Grounding tốt, chỉ thiếu context
Thời gian ước tính: ~3–5 phút/bug
```

**Câu cụ thể nhóm đã debug:**

Câu "Flash Sale hoàn tiền" ban đầu route sai về `retrieval_worker` thay vì `policy_tool_worker`. Nhìn trace thấy ngay: `route_reason="signals: refund_policy[hoàn tiền]"` — keyword "hoàn tiền" đơn thuần trigger refund route nhưng không đủ để vào policy_tool. Sửa: thêm check `decision_signals` trong `_detect_category()` — câu có "Flash Sale" → `policy_exception` → priority cao hơn. Debug time: ~4 phút.

---

## 4. Extensibility Analysis

| Scenario | Day 08 | Day 09 |
|---------|--------|--------|
| Thêm 1 tool/API mới | Phải sửa toàn prompt chuẩn | Thêm 1 function vào `mcp_server.py` + 1 routing rule |
| Thêm 1 domain mới (VD: finance policy) | Phải retrain/re-prompt | Thêm 1 worker mới + keyword group |
| Thay đổi retrieval strategy | Sửa trực tiếp trong pipeline, risk cao | Sửa `workers/retrieval.py` độc lập, test rồi integrate |
| A/B test một phần | Khó — phải clone toàn pipeline | Dễ — swap 1 worker trong graph wrapper |
| Thêm MCP tool mới | Không có cơ chế | `TOOL_REGISTRY["new_tool"] = my_fn` — 3 dòng code |

---

## 5. Cost & Latency Trade-off

| Scenario | Day 08 LLM calls | Day 09 LLM calls |
|---------|-----------------|-----------------|
| Simple query | 1 call | **1 call** (chỉ synthesis) |
| Complex policy query | 1 call | **1 call** (synthesis, policy_tool không gọi LLM) |
| Multi-hop query | 1 call | **1 call** (synthesis) |
| MCP tool call | N/A | **0 LLM calls** (MCP là rule-based/mock) |

**Nhận xét về cost-benefit:**

Đây là **thiết kế hay** của nhóm: supervisor dùng keyword matching (0 LLM calls), MCP tools là rule-based (0 LLM calls), chỉ synthesis mới gọi LLM. Số LLM calls không tăng so với single agent (vẫn là 1 call/query). Latency tăng do Python overhead (~200ms/worker call) và ChromaDB query, không phải do LLM calls.

---

## 6. Kết luận

**Multi-agent tốt hơn single agent ở điểm nào:**

1. **Debuggability:** Trace với route_reason + worker_io_logs giảm debug time từ ~15 phút xuống ~3–5 phút/bug
2. **Multi-hop handling:** Detect cross-domain queries và route đúng, không thể làm được với single pipeline
3. **Extensibility:** Thêm MCP tool hoặc worker mới không cần sửa core pipeline
4. **Anti-hallucination:** Grounded synthesis + abstain condition + confidence signal rõ ràng

**Multi-agent kém hơn hoặc không khác biệt ở điểm nào:**

1. **Simple queries:** Overhead supervisor + worker wrapper (+~200ms) không có giá trị với câu hỏi single-document đơn giản
2. **Initial setup:** Cần thiết kế routing logic, worker contracts, MCP interface — phức tạp hơn nhiều

**Khi nào KHÔNG nên dùng multi-agent:**

Khi domain hẹp, câu hỏi pattern đơn giản, team nhỏ không có bandwidth maintain routing logic. Với < 3 loại query khác nhau, single RAG pipeline đơn giản hơn và dễ maintain hơn đáng kể.

**Nếu tiếp tục phát triển hệ thống này, nhóm sẽ thêm gì:**

Build ChromaDB index đầy đủ với chunking strategy tốt → `avg_confidence` sẽ tăng từ 0.139 lên ~0.7–0.85. Đây là bottleneck lớn nhất hiện tại — routing đúng nhưng synthesis không có evidence để tổng hợp.
