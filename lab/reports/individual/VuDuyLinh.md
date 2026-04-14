# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Vũ Duy Linh  
**Vai trò trong nhóm:** MCP Owner  
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

**Module/file tôi chịu trách nhiệm:**
- File chính: `lab/mcp_server.py`
- Functions tôi implement: Thêm vào và hoàn thiện các chức năng tool cho Mock MCP Server (`tool_search_kb`, `tool_get_ticket_info`, `tool_check_access_permission`, `tool_create_ticket`), hoàn thành Dispatch Layer (`list_tools`, `dispatch_tool`) và thiết lập HTTP FastAPI Server (Bonus Task) để expose API.

**Cách công việc của tôi kết nối với phần của thành viên khác:**

Tôi đảm nhiệm vai trò MCP Owner để xây dựng một Mock MCP Server với mục tiêu cung cấp các API công cụ cho các Agent trong nhóm (do Worker Owner quản lý). Chẳng hạn, khi Agent cần tìm quy trình (SLA) hoặc check quyền ưu tiên của vé, thay vì truy vấn tĩnh, Agent dùng các tools/schemas do tôi định nghĩa để lấy dữ liệu. Việc cung cấp một Dispatch Layer linh hoạt đảm bảo thay đổi ở phía Tool sẽ không tác động đến luồng logic bên Worker Agent.

**Bằng chứng (commit hash, file có comment tên bạn, v.v.):**

Code implementation hoàn chỉnh ở tệp `lab/mcp_server.py`, trong đó tôi đã tự định nghĩa `TOOL_SCHEMAS`, hoàn thiện cơ chế gọi unpack argument và triển khai thành công `app = FastAPI(...)`.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

**Quyết định:** Sử dụng FastAPI (Advanced Option) để cung cấp MCP Tools qua HTTP REST thay vì chỉ dùng dạng Mock Class trực tiếp qua Python CLI (Standard Option).

**Lý do:**
Ban đầu, dùng file pure Python để chạy CLI sẽ đơn giản và an toàn nhất cho việc test Agent. Tuy nhiên trong môi trường sản xuất thực tế (Production), LLM Agent và bộ công cụ thường là microservices phân tán. Do đó, việc xây dựng thẳng một REST Server với FastAPI sẽ giúp mô phỏng cấu trúc thực tế chuẩn xác hơn. Hơn nữa, FastAPI có sẵn cơ chế định dạng HTTP endpoint rất gần gũi với MCP Protocol (như chia route `/tools/list` và `/tools/call`).

**Trade-off đã chấp nhận:**
Sử dụng FastAPI cần thêm dependencies phụ là `uvicorn` và `fastapi`. Thêm vào đó, việc debug sẽ sinh thêm chi phí nhỏ vì có thêm lớp HTTP Status Code và chuyển đổi JSON Payload trong giao tiếp giữa Agent và Server, thay vì chỉ stack trace thuần.

**Bằng chứng từ trace/code:**
Quyết định này được thể hiện rõ ràng trong phần cuối của `mcp_server.py`:
```python
@app.post("/tools/call")
def api_call_tool(request: ToolCallRequest):
    result = dispatch_tool(request.tool_name, request.tool_input)
    if "error" in result and "schema" in result:
        raise HTTPException(status_code=400, detail=result)
    elif "error" in result and "không tồn tại" in result["error"]:
        raise HTTPException(status_code=404, detail=result["error"])
    elif "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    
    return result
```

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

**Lỗi:** Sai lệch chuẩn đầu vào (Schema Validation Error) khi phía Agent gửi sai cấu trúc tham số (tham số không khớp `inputSchema`) vào `dispatch_tool()`, dẫn đến Server bị crash thay vì báo lỗi cho Agent.

**Symptom (pipeline làm gì sai?):**
Khi Agent (vốn không phải luôn tuân thủ đúng schema) gửi request tới tool (ví dụ `check_access_permission`), nếu tham số bị thiếu hoặc sai kiểu, Server sẽ ném thẳng `TypeError` cản trở tiến trình request. Việc này khiến ứng dụng Agent bị "chết" hẳn mà không có cơ hội thử lại qua JSON Error Message.

**Root cause (lỗi nằm ở đâu — indexing, routing, contract, worker logic?):**
Lỗi nằm ở Dispatch Layer của Server (`mcp_server.py`). Khi unpack biến argument `tool_fn(**tool_input)`, hệ thống không hề bắt ngoại lệ nếu tham số do Agent sinh ra bị lệch.

**Cách sửa:**
Tôi bổ sung một khối `try-except TypeError` bọc quanh đoạn thực thi `tool_fn`. Khi có tham số sai, Server sẽ trả về một đối tượng JSON có thuộc tính "error" kèm theo "schema" mô tả định dạng đúng, và được ánh xạ ra HTTP 400 Bad Request, giúp LLM có khả năng đọc lỗi và Self-Correct.

**Bằng chứng trước/sau:**
> Trước khi sửa: Tool gọi ném Exception khiến Server sụp và mất log.
> Sau khi sửa (`mcp_server.py`):
```python
    try:
        result = tool_fn(**tool_input)
        return result
    except TypeError as e:
        return {
            "error": f"Invalid input for tool '{tool_name}': {e}",
            "schema": TOOL_SCHEMAS[tool_name]["inputSchema"],
        }
```

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

**Tôi làm tốt nhất ở điểm nào?**
Tôi đã hoàn thiện tốt việc map cấu trúc Tool Schemas phức tạp theo đúng chuẩn MCP định dạng cho Agent. Giao diện Dispatch HTTP API được thực thi chặt chẽ, bắt lỗi kỹ lưỡng hỗ trợ hệ thống chịu lỗi (Fault tolerance) tốt hơn.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**
Do thời gian xử lý có hạn chế, ở tool `search_kb`, tôi vẫn đang uỷ quyền lại vào Worker `retrieval.py` chứ chưa kết nối độc lập được với nguồn ChromaDB bên dưới. Thêm nữa, phần validate payload bằng Pydantic Model chưa phủ hết hoàn toàn các field trong schema.

**Nhóm phụ thuộc vào tôi ở đâu?** _(Phần nào của hệ thống bị block nếu tôi chưa xong?)_
Nếu tôi chưa hoàn thành cấu trúc `mcp_server.py` thì Agent của nhóm khi Reasoning Tools sẽ không truy xuất được dữ liệu Ticket Database và Access Level, dẫn đến toàn bộ quy trình của Worker bị block cứng.

**Phần tôi phụ thuộc vào thành viên khác:** _(Tôi cần gì từ ai để tiếp tục được?)_
Tôi cần Worker Owner chốt chính xác thư viện LLM Agent có sử dụng chuẩn HTTP payload ra sao để tôi map Request Data cho phù hợp. Đồng thời, tôi cần thêm phản hồi từ Trace Owner về Latency Network khi chạy API ở port 8000.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

Thay vì thiết kế hệ thống giả lập bằng HTTP REST với FastAPI, tôi sẽ bỏ thời gian sử dụng SDK chính thức `mcp` của Python để thiết lập giao thức JSON-RPC qua StdIO (Standard IO) chuẩn. *"Tôi sẽ thử chuyển sang StdIO vì trace system event hiện tại cho thấy TCP request với FastAPI vẫn có overhead nhất định, và chuẩn giao tiếp stdio phổ biến hơn để link vào IDE/VSCode Native MCP."*

---
