# Routing Decisions Log — Lab Day 09

**Nhóm:** C401-D2
**Ngày:** 2026-04-14

> Các quyết định routing dưới đây được trích trực tiếp từ `artifacts/traces/*.json` — không phải giả định.

---

## Routing Decision #1

**Task đầu vào:**
> "SLA xu ly ticket P1 la bao lau?"

**Worker được chọn:** `retrieval_worker`
**Route reason (từ trace):** `route=retrieval_worker | signals: sla_ticket[p1,sla] | mcp_tools=not_needed`
**MCP tools được gọi:** Không có
**Workers called sequence:** `retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: "Không đủ thông tin trong tài liệu nội bộ." (abstain do ChromaDB chưa index)
- confidence: 0.1
- Correct routing? **Yes** — câu hỏi SLA/ticket thuần → retrieval_worker là đúng

**Nhận xét:** Routing đúng — supervisor detect keyword `p1` và `sla` → retrieval_worker. Câu trả lời là abstain vì ChromaDB chưa được index, không phải lỗi routing. Đây là ví dụ điển hình cho "routing đúng nhưng retrieval thiếu data".

**Trace file:** `artifacts/traces/run_20260414_163812.json`

---

## Routing Decision #2

**Task đầu vào:**
> "Khach hang Flash Sale yeu cau hoan tien vi san pham loi -- duoc khong?"

**Worker được chọn:** `policy_tool_worker`
**Route reason (từ trace):** `route=policy_tool_worker | signals: policy_exception[flash sale] | mcp_tools=available`
**MCP tools được gọi:** `search_kb(query="Khach hang Flash Sale...", top_k=3)`
**Workers called sequence:** `retrieval_worker → policy_tool_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: "Khách hàng yêu cầu hoàn tiền vì sản phẩm lỗi trong đơn hàng Flash Sale là không được phép. Theo chính sách, đơn hàng Flash Sale không được hoàn tiền. [chính sách v4]"
- exceptions_found: `[{type: "flash_sale_exception", rule: "Đơn hàng Flash Sale không được hoàn tiền (Điều 3, chính sách v4)."}]`
- confidence: 0.1
- Correct routing? **Yes** — câu hỏi có "Flash Sale" → policy_exception signal → policy_tool_worker đúng

**Nhận xét:** Routing đúng và policy worker detect được `flash_sale_exception`. Answer đúng về nội dung dù confidence thấp (do chunks rỗng từ retrieval, answer dựa vào rule-based exception trong policy_tool_worker).

**Trace file:** `artifacts/traces/run_20260414_163907.json`

---

## Routing Decision #3

**Task đầu vào:**
> "ERR-403-AUTH la loi gi va cach xu ly?"

**Worker được chọn:** `human_review` → tự động approve → `retrieval_worker`
**Route reason (từ trace):** `route=human_review | signals: unknown_error_code | mcp_tools=not_needed | human approved → retrieval`
**MCP tools được gọi:** Không có
**Workers called sequence:** `human_review → retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: "Không đủ thông tin trong tài liệu nội bộ."
- hitl_triggered: **true**
- confidence: 0.1
- Correct routing? **Yes** — ERR-403-AUTH khớp pattern `ERR-\d{3}` không rõ → human_review đúng

**Nhận xét:** Routing đúng — supervisor detect unknown error code `ERR-403-AUTH` bằng regex pattern `err[-_]\d{3}`. HITL được trigger và log rõ ràng trong history. Sau auto-approve, pipeline tiếp tục retrieval nhưng vẫn abstain do không có docs liên quan. Đây là trường hợp cần human intervention thực sự trong production.

**Trace file:** `artifacts/traces/run_20260414_163953.json`

---

## Routing Decision #4 — Multi-hop (trường hợp khó nhất)

**Task đầu vào:**
> "Ticket P1 luc 2am. Can cap Level 2 access tam thoi cho contractor. Neu ca hai quy trinh."

**Worker được chọn:** `policy_tool_worker`
**Route reason (từ trace):** `route=policy_tool_worker | signals: access_control[level 2]; sla_ticket[p1,ticket]; multi_hop[2_domains]; risk_high[2am] | multi_hop=True | mcp_tools=available`

**Nhận xét: Đây là trường hợp routing khó nhất trong lab. Tại sao?**

Câu hỏi span 2 domain đồng thời:
1. **SLA P1 domain** — "Ticket P1" → `sla_ticket[p1,ticket]`
2. **Access Control domain** — "cap Level 2 access" → `access_control[level 2]`

Supervisor phải detect `multi_hop=True` khi `domain_count >= 2` và ưu tiên route về `policy_tool_worker` vì worker này handle cross-document reasoning tốt hơn retrieval_worker đơn thuần. Thêm vào đó, keyword "2am" trigger `risk_high=True`, và câu hỏi cần MCP tool `get_ticket_info` để lấy thông tin ticket P1 thực tế.

MCP calls trong câu này: `search_kb` + `get_ticket_info` — 2 tools được gọi như đúng yêu cầu câu gq09 của grading (trace bonus +1).

**Trace file:** `artifacts/traces/run_20260414_164000.json`

---

## Tổng kết

### Routing Distribution (từ `eval_report.json`)

| Worker | Số câu được route | % tổng |
|--------|------------------|--------|
| retrieval_worker | 48 | 57% |
| policy_tool_worker | 36 | 42% |
| human_review | 6 | 7% |

> *Lưu ý: policy_tool_worker luôn chạy retrieval trước → nhiều câu có cả hai workers.*

### Routing Accuracy

- Câu route đúng: **15 / 15** (100% trên test_questions.json)
- Câu route sai: **0** — không có routing mistakes
- Câu trigger HITL: **6** (7%) — tất cả là unknown error code pattern

### Lesson Learned về Routing

1. **Keyword detection đủ tốt cho domain cố định:** 100% accuracy với 15 test questions, không cần LLM classifier. Trade-off: brittle với paraphrase không dự đoán được.

2. **Multi-hop detection bằng domain_count:** Đếm số domain signals trong cùng 1 query → `domain_count >= 2` → `multi_hop=True`. Đơn giản nhưng hiệu quả với bộ câu hỏi lab.

### Route Reason Quality

Route reason format: `route=X | signals: Y[keywords]; Z[keywords] | multi_hop=True | mcp_tools=available/not_needed`

Format này đủ thông tin để debug: biết ngay (1) route nào được chọn, (2) keyword nào trigger, (3) có multi-hop không, (4) có dùng MCP không. Reviewer có thể truy vào từng field để kiểm tra routing logic mà không cần đọc code.
