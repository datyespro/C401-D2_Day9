# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nguyễn Anh Đức (2A202600387)
**Vai trò trong nhóm:** Documentation & Synthesis Owner (M6)
**Ngày nộp:** 14/04/2026

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `workers/synthesis.py`
- Functions tôi implement:
  - `_call_llm(messages)` — gọi LLM (OpenAI ưu tiên, Gemini fallback) với API key validation
  - `_build_context(chunks, policy_result)` — xây dựng context block có cấu trúc từ retrieved chunks và policy exceptions
  - `_estimate_confidence(chunks, answer, policy_result)` — tính confidence score thực tế từ 6 tín hiệu (không hard-code)
  - `synthesize(task, chunks, policy_result)` — hàm core tổng hợp
  - `run(state)` — entry point kết nối với graph.py

Ngoài ra tôi chịu trách nhiệm toàn bộ thư mục `docs/` (3 file tài liệu kỹ thuật) và `reports/group_report.md`.

**Cách công việc của tôi kết nối với phần của thành viên khác:**

Synthesis worker là **bước cuối cùng trong mọi pipeline route**. Tôi đọc đầu ra của cả retrieval_worker (Hoàng Ngọc Anh) và policy_tool_worker (Nguyễn Hoàng Việt), tổng hợp thành `final_answer` với citation. Nếu synthesis fail, toàn bộ pipeline không có output. Đồng thời, sau khi Đậu Văn Quyền (M5 — Trace Owner) chạy `eval_trace.py` và sinh ra `artifacts/traces/*.json` và `artifacts/eval_report.json`, tôi mới có số liệu để điền vào `docs/`.

**Bằng chứng:**
- File `workers/synthesis.py` có header `Author: Documentation & Synthesis Owner - Nguyễn Anh Đức (M6)`
- Commit chứa toàn bộ `workers/synthesis.py` và thư mục `docs/`, `reports/`

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Tính `confidence` bằng 6 tín hiệu thực tế thay vì return một giá trị cố định.

**Bối cảnh vấn đề:**

Template gốc của `_estimate_confidence()` chỉ trả về `min(0.95, avg_score - exception_penalty)`. Khi ChromaDB trả về `score=0` (chưa index) thì confidence cũng về 0, không phân biệt được câu abstain với câu có context thực sự kém. Khi test, tôi thấy câu SLA P1 và câu "mức phạt SLA" (không có trong docs) đều có `confidence=0.1` — không thể phân biệt được hai trường hợp này qua trace.

**Các lựa chọn đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|------------|
| Hard-code giá trị (0.9 nếu có chunks, 0.1 nếu không) | Đơn giản, nhanh | Không phản ánh thực tế, không đạt bonus +1 |
| Dùng LLM-as-Judge gọi thêm 1 LLM call để đánh giá | Chính xác nhất | Tốn thêm 1 API call, tăng latency ~1s |
| **6-signal heuristic** (phương án đã chọn) | Không tốn thêm API, phản ánh data thực | Vẫn là heuristic, chưa perfect |

**Phương án đã chọn và lý do:** 6-signal heuristic vì không tốn thêm LLM call nhưng vẫn đạt bonus +1 theo SCORING.md ("confidence score thực tế, không hard-code").

**6 tín hiệu:** chunk avg score (weight 70%) + chunk quantity bonus + answer length factor − exception penalty, với 2 ngưỡng override (no chunks → 0.1, abstain keywords → 0.25).

**Bằng chứng từ test độc lập:**

```
[Test 1] SLA P1 (chunks có score=0.92)
  Confidence: 0.95  ← phản ánh evidence tốt

[Test 3] Abstain - không có docs
  Confidence: 0.1   ← phản ánh không có evidence

[Test 2] Flash Sale exception
  Confidence: 0.90  ← có chunk nhưng có exception penalty
```

**Trade-off đã chấp nhận:** Heuristic có thể sai trong edge case. Nếu có thêm thời gian, sẽ upgrade lên LLM-as-Judge.

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** `_call_llm()` gọi API ngay cả khi key là placeholder `sk-...your-key-here...`, gây lỗi `openai.AuthenticationError` và exception bị nuốt bởi `except Exception: pass` → trả về fallback error âm thầm, không báo lỗi rõ ràng.

**Symptom:** Chạy `python workers/synthesis.py` với `.env` chưa điền key thật → in ra `[SYNTHESIS ERROR] Không thể gọi LLM...` không có thông tin debug.

**Root cause:** Template gốc không kiểm tra giá trị của API key trước khi gọi, chỉ kiểm tra package có import được không. Khi key là placeholder, OpenAI library nhận key nhưng server từ chối → raise `AuthenticationError` → bị `except Exception: pass` nuốt mất.

**Cách sửa:** Thêm guard check trước mỗi provider:

```python
# Trước (lỗi):
try:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))  # gọi dù key là placeholder
    ...

# Sau (đã sửa):
openai_key = os.getenv("OPENAI_API_KEY", "")
if openai_key and openai_key != "sk-...your-key-here...":
    try:
        from openai import OpenAI
        ...
    except Exception as e:
        print(f"  ⚠️  OpenAI call failed: {e}. Trying Gemini...")
```

**Bằng chứng:** Sau khi sửa, chạy với key thật → test pass, print warning rõ ràng khi fail thay vì âm thầm.

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở điểm nào:**
Thiết kế `_estimate_confidence()` với 6 tín hiệu thực tế — đây là điểm khác biệt quan trọng giúp đạt bonus điểm và làm trace có ý nghĩa hơn. Tài liệu `docs/` được điền dựa vào số liệu thực từ trace, không phải ước đoán.

**Tôi làm chưa tốt hoặc còn yếu:**
Synthesis worker chưa implement được "LLM-as-Judge" để tính confidence chính xác hơn. Khi ChromaDB chưa index đầy đủ (retrieved_chunks = []), synthesis phải abstain — đây không hẳn là lỗi của synthesis_worker nhưng làm confidence thấp toàn bộ.

**Nhóm phụ thuộc vào tôi ở đâu:**
Mọi route đều kết thúc tại `synthesis_worker` — nếu `run(state)` lỗi, cả pipeline không có `final_answer`. Phần docs cũng phụ thuộc vào tôi để giảng viên hiểu kiến trúc toàn hệ thống.

**Phần tôi phụ thuộc vào thành viên khác:**
Tôi cần Đậu Văn Quyền chạy `eval_trace.py` xong và cung cấp `artifacts/eval_report.json` + `artifacts/traces/*.json` mới điền được `docs/routing_decisions.md` và `docs/single_vs_multi_comparison.md` với số liệu thật.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ upgrade `_estimate_confidence()` thành **LLM-as-Judge**: sau khi synthesis_worker tạo ra `final_answer`, gọi thêm 1 LLM call ngắn để tự đánh giá độ tin cậy của câu trả lời dựa trên context. Lý do: trace của câu hỏi về "mức phạt SLA P1" (`run_20260414_163953.json`) cho thấy synthesis đang abstain đúng (`confidence=0.1`) nhưng với lý do là không có chunks — không phải vì LLM tự nhận biết thông tin không có. LLM-as-Judge sẽ cho phép phân biệt "không có context" với "context không đủ để trả lời chính xác" — hai trường hợp có mức rủi ro hallucination khác nhau.

---

*File lưu tại: `reports/individual/NguyenAnhDuc.md`*
*Commit sau 18:00 được phép theo SCORING.md*
