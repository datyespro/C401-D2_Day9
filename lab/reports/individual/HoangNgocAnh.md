# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Hoàng Ngọc Anh
**Vai trò trong nhóm:** Worker Owner 
**Ngày nộp:** 14/4/2026  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

> Trong dự án Multi-Agent lần này, tôi chịu trách nhiệm chính trong việc xây dựng khả năng "ghi nhớ" và "tra cứu" thông tin cho hệ thống thông qua Retrieval Worker.

**Module/file tôi chịu trách nhiệm:**
- File chính: `workers/retrieval.py`
- Functions tôi implement: 
    - `_get_embedding_fn()`: Khởi tạo mô hình embedding (hỗ trợ cả OpenAI và fallback).
    - `retrieve_dense()`: Thực hiện truy vấn vector trên ChromaDB.
    - `run()`: Entry point chính theo đúng Worker Contract để kết nối với LangGraph.

**Cách công việc của tôi kết nối với phần của thành viên khác:**

Tôi nhận yêu cầu từ **Supervisor Owner** sau khi họ phân loại ý định người dùng. Kết quả đầu ra của tôi (`retrieved_chunks`) là đầu vào bắt buộc cho **Generator Worker** để họ thực hiện trả lời dựa trên ngữ cảnh (RAG). 


**Bằng chứng (commit hash, file có comment tên bạn, v.v.):**

Tôi đã implement cấu trúc `worker_io` trong hàm `run` để lưu lại `chunks_count` và `sources`, khớp với contract đã thống nhất trong file `contracts/worker_contracts.yaml`.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

**Quyết định:** Tôi quyết định triển khai cơ chế **Multi-level Embedding Fallback** trong hàm `_get_embedding_fn` và chuyển đổi **Distance sang Similarity Score**.

**Lý do:**

Trong quá trình phát triển, việc phụ thuộc hoàn toàn vào OpenAI API (`text-embedding-3-small`) gây ra rủi ro bị block do hết hạn quota hoặc mất mạng, làm gián đoạn công việc của các thành viên khác. Tôi đã thiết kế để hệ thống ưu tiên OpenAI, nếu lỗi sẽ tìm đến `sentence-transformers` (chạy local), và cuối cùng là một hàm sinh vector ngẫu nhiên để đảm bảo pipeline không bao giờ bị "crash" ngang xương. 

Ngoài ra, ChromaDB mặc định trả về `distance` (càng nhỏ càng tốt), nhưng để các worker phía sau (như Generator) dễ dàng đánh giá độ tin cậy, tôi đã thực hiện công thức `score = round(1 - dist, 4)`.


**Trade-off đã chấp nhận:** Việc dùng random embeddings làm fallback sẽ khiến kết quả RAG sai lệch hoàn toàn, nhưng nó giúp team Supervisor và Graph có thể test luồng logic (flow) mà không bị chặn bởi lỗi thư viện.

**Bằng chứng từ trace/code:**

```
python
# Cách tôi chuyển đổi score để dễ đọc hơn trong trace
chunks.append({
    "text": doc,
    "source": meta.get("source", "unknown"),
    "score": round(1 - dist, 4),  # Chuyển từ distance sang cosine similarity
    "metadata": meta,
})
```

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

**Lỗi:** `IndexError: list index out of range` khi truy vấn ChromaDB với một database trống hoặc không tìm thấy kết quả phù hợp.

**Symptom (pipeline làm gì sai?):** Khi Supervisor gửi một câu hỏi hoàn toàn không liên quan đến dữ liệu (ví dụ: "Hôm nay ăn gì?"), hàm `retrieve_dense` gọi `results["documents"][0]` bị văng lỗi vì list `documents` trả về là một list rỗng bên trong `[[]]`.


**Root cause (lỗi nằm ở đâu — indexing, routing, contract, worker logic?):** Cấu trúc trả về của ChromaDB là dạng batch (cho phép query nhiều câu cùng lúc). Khi chỉ query 1 câu, nó trả về list lồng nhau. Nếu không có kết quả, index `[0]` sẽ không tồn tại.


**Cách sửa:** Tôi đã bọc toàn bộ logic truy vấn vào block `try-except` và thêm kiểm tra logic trước khi truy cập index. Nếu có lỗi, thay vì để hệ thống sập, tôi trả về một list rỗng và ghi log lỗi rõ ràng vào `state["history"]`.

**Bằng chứng trước/sau:**
- **Trước:** `results["documents"][0]` -> Gây crash app nếu db trống.
- **Sau:** 

```python
try:
    results = collection.query(...)
    # ... logic duyệt zip(results["documents"][0], ...)
except Exception as e:
    print(f"⚠️  ChromaDB query failed: {e}")
    return [] # Trả về list rỗng an toàn
```
Trace sau khi sửa: `[retrieval_worker] retrieved 0 chunks from []`, hệ thống vẫn chạy tiếp đến node tiếp theo.


## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

> Trả lời trung thực — không phải để khen ngợi bản thân.

**Tôi làm tốt nhất ở điểm nào?**

Tôi đã xây dựng được một Worker có tính chịu lỗi (resilience) tốt. Việc tách biệt hàm `retrieve_dense` giúp việc unit test độc lập rất dễ dàng (như phần `if __name__ == "__main__":` tôi đã viết cuối file).


**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

Tôi chưa tối ưu được tốc độ truy vấn. Mặc dù đã dùng ChromaDB, nhưng việc khởi tạo client và load collection trong mỗi lần gọi `run()` có thể gây độ trễ. Nếu hệ thống scale lớn, tôi cần refactor để giữ kết nối DB persistent.

**Nhóm phụ thuộc vào tôi ở đâu?** _(Phần nào của hệ thống bị block nếu tôi chưa xong?)_

Nhóm Generator Worker hoàn toàn phụ thuộc vào đầu ra của tôi. Nếu `retrieved_chunks` rỗng hoặc sai, câu trả lời cuối cùng sẽ không có cơ sở dữ liệu để trích dẫn.

**Phần tôi phụ thuộc vào thành viên khác:** _(Tôi cần gì từ ai để tiếp tục được?)_

Tôi phụ thuộc vào Supervisor Worker để nhận được câu hỏi đã được phân loại và làm sạch. Nếu Supervisor không phân loại đúng hoặc không gửi đủ context, Worker của tôi sẽ không biết phải tìm kiếm gì.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

> Nêu **đúng 1 cải tiến** với lý do có bằng chứng từ trace hoặc scorecard.
> Không phải "làm tốt hơn chung chung" — phải là:
> *"Tôi sẽ thử X vì trace của câu gq___ cho thấy Y."*

Tôi sẽ refactor lại hàm `run` để tách biệt việc khởi tạo client và việc query. Hiện tại, `chromadb.Client()` được gọi mỗi lần worker chạy, gây lãng phí tài nguyên. Tôi sẽ di chuyển việc khởi tạo lên class constructor hoặc dùng singleton pattern để đảm bảo client chỉ được tạo một lần duy nhất.

---

*Lưu file này với tên: `reports/individual/[ten_ban].md`*  
*Ví dụ: `reports/individual/nguyen_van_a.md`*
