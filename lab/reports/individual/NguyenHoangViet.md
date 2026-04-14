# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nguyễn Hoàng Việt 
**Vai trò trong nhóm:**  Worker Owner(policy_tool)
**Ngày nộp:** 14/04/2026  
**Độ dài yêu cầu:** 500–800 từ

---

> **Lưu ý quan trọng:**
> - Viết ở ngôi **"tôi"**, gắn với chi tiết thật của phần bạn làm
> - Phải có **bằng chứng cụ thể**: tên file, đoạn code, kết quả trace, hoặc commit
> - Nội dung phân tích phải khác hoàn toàn với các thành viên trong nhóm
> - Deadline: Được commit **sau 18:00** (xem SCORING.md)
> - Lưu file với tên: `reports/individual/[ten_ban].md` (VD: `nguyen_van_a.md`)

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

Trong lab Day 09, tôi phụ trách worker policy_tool trong pipeline multi-agent. Cụ thể, tôi làm phần kiểm tra điều kiện áp dụng policy hoàn tiền và phát hiện ngoại lệ theo rule-based trước khi synthesis tạo câu trả lời cuối cùng. Tôi tập trung vào logic phân tích policy theo từ khóa nghiệp vụ (Flash Sale, license key/subscription, đã kích hoạt) và cơ chế ghi lại kết quả policy_result để các worker phía sau dùng lại được. Tôi cũng tham gia phần kết nối MCP theo hướng “có thể mở rộng”, tức là để sẵn lớp gọi tool, xử lý lỗi tool call và ghi log tool usage vào state nhằm phục vụ debug trace.

**Module/file tôi chịu trách nhiệm:**
- File chính: `lab/workers/policy_tool.py`
- Functions tôi implement: `analyze_policy`, `run`, `_call_mcp_tool`

**Cách công việc của tôi kết nối với phần của thành viên khác:**

Phần của tôi nhận input từ supervisor (route, needs_tool) và retrieval_worker (retrieved_chunks). Sau đó policy_tool_worker trả policy_result cho synthesis_worker để tạo final_answer có căn cứ policy rõ hơn. Nếu policy_tool trả sai ngoại lệ thì câu trả lời cuối dễ bị lệch logic dù retrieval đúng.

**Bằng chứng (commit hash, file có comment tên bạn, v.v.):**

- 4e420c4ccbfad2f72213313c5c300139c8bb56ca
- 53b37a36890fd007960b9fb484e468a9054de515
- 81f8284541d44704229039cc08fde565e7f8b72b
- ab98324c43dea35bc19a886b7b2e08c8be47a06c
---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

> Chọn **1 quyết định** bạn trực tiếp đề xuất hoặc implement trong phần mình phụ trách.
> Giải thích:
> - Quyết định là gì?
> - Các lựa chọn thay thế là gì?
> - Tại sao bạn chọn cách này?
> - Bằng chứng từ code/trace cho thấy quyết định này có effect gì?

**Quyết định:** Dùng rule-based policy analysis trong policy_tool_worker thay vì gọi LLM trực tiếp ở bước phân tích policy.

**Ví dụ:**
> "Tôi chọn dùng keyword-based routing trong supervisor_node thay vì gọi LLM để classify.
>  Lý do: keyword routing nhanh hơn (~5ms vs ~800ms) và đủ chính xác cho 5 categories.
>  Bằng chứng: trace gq01 route_reason='task contains P1 SLA keyword', latency=45ms."

**Lý do:**

Tôi chọn cách rule-based trước vì ba lý do. Thứ nhất, policy exception của bài lab có cấu trúc khá rõ (Flash Sale, digital product, activated), nên có thể biểu diễn bằng luật deterministic và dễ kiểm thử hơn. Thứ hai, trace của hệ thống multi-agent đã có độ trễ trung bình khá cao , nên nếu thêm một lượt LLM nữa ở policy worker thì latency sẽ tăng đáng kể. Thứ ba, rule-based cho phép tôi ghi rõ “vì sao bị chặn” bằng exception type/rule/source, giúp debug tốt hơn khi so với một kết quả free-form từ model.

**Trade-off đã chấp nhận:**

Trade-off là độ phủ ngữ nghĩa không cao bằng LLM: cùng một ý nhưng diễn đạt khác có thể không match keyword. Ngoài ra, rule-based dễ phát sinh false positive nếu không khống chế phạm vi kiểm tra từ task và context hợp lý.

**Bằng chứng từ trace/code:**

```
# lab/workers/policy_tool.py
if "flash sale" in task_lower or "flash sale" in context_text:
	exceptions_found.append({...})

if any(kw in task_lower for kw in ["license key", "license", "subscription", "kỹ thuật số"]):
	exceptions_found.append({...})

# q07 trace (run_20260414_171005)
[policy_tool_worker] policy_applies=False, exceptions=2

# eval_report
"routing_accuracy_pct": 100.0,
"routing_distribution": {"policy_tool_worker": "36/84 (42%)"}
```

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

> Mô tả 1 bug thực tế bạn gặp và sửa được trong lab hôm nay.
> Phải có: mô tả lỗi, symptom, root cause, cách sửa, và bằng chứng trước/sau.

**Lỗi:** Bắt nhầm ngoại lệ Flash Sale (false positive) trong câu hỏi không yêu cầu điều kiện Flash Sale.

**Symptom (pipeline làm gì sai?):**

Ở câu q07 “Sản phẩm kỹ thuật số (license key) có được hoàn tiền không?”, policy worker trả exceptions_count=2 gồm cả digital_product_exception và flash_sale_exception. Về nghiệp vụ, câu hỏi này chỉ cần kết luận theo ngoại lệ sản phẩm kỹ thuật số; việc thêm Flash Sale làm phần giải thích bị nhiễu, gây cảm giác policy engine suy luận sai trọng tâm.

**Root cause (lỗi nằm ở đâu — indexing, routing, contract, worker logic?):**

Root cause nằm ở worker logic trong analyze_policy: điều kiện Flash Sale đang kiểm tra cả task và toàn bộ context_text. Trong khi chunk policy_refund_v4 luôn chứa cụm “Flash Sale”, nên chỉ cần retrieval trả tài liệu này là rule Flash Sale dễ bị kích hoạt dù câu hỏi không đề cập trực tiếp.

**Cách sửa:**

Tôi chỉnh cách diễn giải và ưu tiên ngoại lệ khi tổng hợp policy_result: giữ rule chính bám theo tín hiệu task, đồng thời bổ sung temporal scoping rõ ràng hơn ở q12 để tránh trả lời quá chắc chắn khi thiếu policy v3. Hướng tiếp theo tôi đề xuất là tách trigger từ task và trigger từ context thành hai mức confidence khác nhau để giảm false positive hệ thống.

**Bằng chứng trước/sau:**
> Dán trace/log/output trước khi sửa và sau khi sửa.

Trước (q07 run_20260414_165839):
`[policy_tool_worker] policy_applies=False, exceptions=2` với `flash_sale_exception` + `digital_product_exception`.

Sau (q12 run_20260414_171021 - temporal case):
`exceptions_found` có bổ sung `temporal_scoping_exception` và `policy_version_note` nêu rõ đơn trước 01/02/2026 phải theo policy v3, giúp câu trả lời chuyển sang hướng “không đủ thông tin v3” thay vì khẳng định theo v4.

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

> Trả lời trung thực — không phải để khen ngợi bản thân.

**Tôi làm tốt nhất ở điểm nào?**

Tôi làm tốt nhất ở phần biến policy logic thành output có cấu trúc, dễ debug và dễ nối với worker khác. Cụ thể là policy_result có policy_applies, exceptions_found, source, policy_version_note nên synthesis có đủ dữ liệu để giải thích câu trả lời thay vì chỉ trả yes/no.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

Tôi chưa làm tốt ở độ tinh của rule. Một số trigger còn rộng (đặc biệt khi quét toàn bộ context) nên có thể sinh false positive. Ngoài ra, tôi mới dừng ở rule-based, chưa tích hợp LLM fallback cho trường hợp diễn đạt phức tạp.

**Nhóm phụ thuộc vào tôi ở đâu?** _(Phần nào của hệ thống bị block nếu tôi chưa xong?)_

Nếu policy_tool_worker chưa ổn thì các câu thuộc Refund/Access Control sẽ trả lời thiếu căn cứ hoặc sai ngoại lệ; nhóm sẽ khó chứng minh năng lực orchestration vì trace không thể hiện được policy reasoning.

**Phần tôi phụ thuộc vào thành viên khác:** _(Tôi cần gì từ ai để tiếp tục được?)_

Tôi phụ thuộc vào retrieval_worker để lấy đúng chunk policy và phụ thuộc synthesis_worker để trình bày kết luận đúng trọng tâm từ policy_result. Ngoài ra, tôi cần supervisor route chính xác để không bị gọi policy worker ở câu pure retrieval.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

> Nêu **đúng 1 cải tiến** với lý do có bằng chứng từ trace hoặc scorecard.
> Không phải "làm tốt hơn chung chung" — phải là:
> *"Tôi sẽ thử X vì trace của câu gq___ cho thấy Y."*

Tôi sẽ sửa triệt để lỗi false positive Flash Sale bằng cách chỉ kích hoạt flash_sale_exception khi tín hiệu xuất hiện trong task hoặc metadata đơn hàng, không kích hoạt chỉ vì cụm từ có trong chunk policy. Lý do là trace q07 cho thấy exceptions_count=2 dù câu hỏi chỉ xoay quanh license key. Nếu sửa điểm này, phần giải thích sẽ sạch hơn và confidence của synthesis có thể tăng do ít nhiễu logic.

---

*Lưu file này với tên: `reports/individual/[ten_ban].md`*  
*Ví dụ: `reports/individual/nguyen_van_a.md`*
