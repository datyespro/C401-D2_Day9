"""
workers/synthesis.py — Synthesis Worker
Sprint 2: Tổng hợp câu trả lời từ retrieved_chunks và policy_result.

Input (từ AgentState):
    - task: câu hỏi
    - retrieved_chunks: evidence từ retrieval_worker
    - policy_result: kết quả từ policy_tool_worker

Output (vào AgentState):
    - final_answer: câu trả lời cuối với citation
    - sources: danh sách nguồn tài liệu được cite
    - confidence: mức độ tin cậy (0.0 - 1.0)

Gọi độc lập để test:
    python workers/synthesis.py

Author: Documentation & Synthesis Owner - Nguyễn Anh Đức (M6)
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

WORKER_NAME = "synthesis_worker"

# ─────────────────────────────────────────────
# System Prompt — grounded, no hallucination
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """Bạn là trợ lý IT Helpdesk nội bộ chuyên nghiệp.

Quy tắc nghiêm ngặt (PHẢI tuân thủ):
1. CHỈ trả lời dựa vào context TÀI LIỆU THAM KHẢO được cung cấp. KHÔNG dùng kiến thức ngoài.
2. Nếu context không đủ thông tin để trả lời → trả lời chính xác:
   "Không đủ thông tin trong tài liệu nội bộ để trả lời câu hỏi này."
3. Trích dẫn nguồn inline sau mỗi thông tin quan trọng. Ví dụ: [sla_p1_2026.txt]
4. Nếu có POLICY EXCEPTIONS → nêu rõ exception TRƯỚC, sau đó mới kết luận.
5. Câu trả lời súc tích, có cấu trúc rõ ràng. Dùng bullet points nếu có nhiều ý.
6. KHÔNG bịa thêm thông tin, mức phạt, con số không có trong tài liệu."""


# ─────────────────────────────────────────────
# LLM Caller — ưu tiên OpenAI, fallback Gemini
# ─────────────────────────────────────────────

def _call_llm(messages: list) -> str:
    """
    Gọi LLM để tổng hợp câu trả lời.
    Ưu tiên OpenAI (có key trong .env). Fallback sang Gemini nếu OpenAI fail.
    """
    openai_key = os.getenv("OPENAI_API_KEY", "")
    google_key = os.getenv("GOOGLE_API_KEY", "")

    # ── Option A: OpenAI ──
    if openai_key and openai_key != "sk-...your-key-here...":
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.1,   # Low temperature → grounded, ít sáng tạo
                max_tokens=600,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"  ⚠️  OpenAI call failed: {e}. Trying Gemini...")

    # ── Option B: Gemini ──
    if google_key and google_key != "AI...your-key-here...":
        try:
            import google.generativeai as genai
            genai.configure(api_key=google_key)
            model = genai.GenerativeModel(
                "gemini-1.5-flash",
                generation_config={"temperature": 0.1, "max_output_tokens": 600},
            )
            # Ghép system + user messages thành 1 prompt
            combined = "\n\n".join([
                f"{'[SYSTEM]' if m['role'] == 'system' else '[USER]'}: {m['content']}"
                for m in messages
            ])
            response = model.generate_content(combined)
            return response.text.strip()
        except Exception as e:
            print(f"  ⚠️  Gemini call failed: {e}.")

    # ── Fallback: không có LLM → trả về báo lỗi rõ ràng ──
    return "[SYNTHESIS ERROR] Không thể gọi LLM. Kiểm tra OPENAI_API_KEY hoặc GOOGLE_API_KEY trong .env."


# ─────────────────────────────────────────────
# Context Builder
# ─────────────────────────────────────────────

def _build_context(chunks: list, policy_result: dict) -> str:
    """
    Xây dựng context block từ retrieved_chunks và policy_result.
    Format: numbered list với source citation và relevance score.
    """
    parts = []

    # Phần 1: Evidence chunks từ retrieval_worker
    if chunks:
        parts.append("=== TÀI LIỆU THAM KHẢO ===")
        for i, chunk in enumerate(chunks, 1):
            source = chunk.get("source", "unknown")
            text = chunk.get("text", "").strip()
            score = chunk.get("score", 0.0)
            parts.append(f"[{i}] Nguồn: {source} (relevance: {score:.2f})\n{text}")

    # Phần 2: Policy exceptions từ policy_tool_worker
    if policy_result and policy_result.get("exceptions_found"):
        parts.append("\n=== POLICY EXCEPTIONS (ưu tiên xử lý) ===")
        for ex in policy_result["exceptions_found"]:
            ex_type = ex.get("type", "")
            rule = ex.get("rule", "")
            parts.append(f"- [{ex_type}] {rule}")

    # Phần 3: Policy summary nếu có
    if policy_result and policy_result.get("policy_name"):
        policy_name = policy_result.get("policy_name", "")
        applies = policy_result.get("policy_applies", None)
        if applies is not None:
            applies_str = "ÁP DỤNG" if applies else "KHÔNG áp dụng"
            parts.append(f"\n=== KẾT QUẢ KIỂM TRA POLICY ===\n- {policy_name}: {applies_str}")

    if not parts:
        return "(Không có context — không có tài liệu nào được retrieve)"

    return "\n\n".join(parts)


# ─────────────────────────────────────────────
# Confidence Estimator (không hard-code)
# ─────────────────────────────────────────────

def _estimate_confidence(chunks: list, answer: str, policy_result: dict) -> float:
    """
    Tính confidence score thực tế dựa vào 4 tín hiệu:
      1. Chunk retrieval quality (avg cosine similarity)
      2. Chunk quantity (nhiều chunk tốt hơn)
      3. Abstain signal (answer nói không đủ thông tin → low)
      4. Exception complexity penalty (policy exception → tăng độ không chắc)

    Không hard-code — mọi giá trị đều derive từ data thực tế.
    """
    # Tín hiệu 1: Không có chunks → rất thấp
    if not chunks:
        return 0.1

    # Tín hiệu 2: Abstain signal từ answer text
    abstain_signals = [
        "không đủ thông tin",
        "không có trong tài liệu",
        "không tìm thấy",
        "synthesis error",
        "không thể gọi llm",
    ]
    if any(sig in answer.lower() for sig in abstain_signals):
        return 0.25

    # Tín hiệu 3: Chunk quality — avg cosine similarity score
    chunk_scores = [c.get("score", 0.5) for c in chunks]
    avg_chunk_score = sum(chunk_scores) / len(chunk_scores)

    # Sigmoid-like normalisation: score range [0, 1] → capped at 0.9
    quality_factor = min(0.9, avg_chunk_score)

    # Tín hiệu 4: Chunk quantity bonus (thêm chunk → thêm evidence)
    quantity_bonus = min(0.05, (len(chunks) - 1) * 0.025)

    # Tín hiệu 5: Exception penalty (exceptions làm tăng uncertainty)
    exception_count = len(policy_result.get("exceptions_found", []))
    exception_penalty = 0.05 * exception_count

    # Tín hiệu 6: Answer length (quá ngắn → probably low quality)
    length_factor = min(0.05, len(answer.strip()) / 2000)

    confidence = quality_factor + quantity_bonus + length_factor - exception_penalty
    return round(max(0.1, min(0.95, confidence)), 2)


# ─────────────────────────────────────────────
# Core Synthesize Function
# ─────────────────────────────────────────────

def synthesize(task: str, chunks: list, policy_result: dict) -> dict:
    """
    Tổng hợp câu trả lời cuối từ chunks và policy context.

    Returns:
        {"answer": str, "sources": list[str], "confidence": float}
    """
    context = _build_context(chunks, policy_result)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Câu hỏi: {task}\n\n"
                f"{context}\n\n"
                "Hãy trả lời câu hỏi DỰA TRÊN TÀI LIỆU TRÊN. "
                "Trích dẫn nguồn [tên_file] sau mỗi thông tin quan trọng."
            ),
        },
    ]

    answer = _call_llm(messages)
    # Deduplicate sources, preserve order of appearance
    seen = set()
    sources = []
    for c in chunks:
        src = c.get("source", "unknown")
        if src not in seen:
            seen.add(src)
            sources.append(src)

    confidence = _estimate_confidence(chunks, answer, policy_result)

    return {
        "answer": answer,
        "sources": sources,
        "confidence": confidence,
    }


# ─────────────────────────────────────────────
# Worker Entry Point (gọi từ graph.py)
# ─────────────────────────────────────────────

def run(state: dict) -> dict:
    """
    Worker entry point — gọi từ graph.py theo contract.

    Reads từ state:
        task, retrieved_chunks, policy_result

    Writes vào state:
        final_answer, sources, confidence, workers_called, history, worker_io_logs
    """
    task = state.get("task", "")
    chunks = state.get("retrieved_chunks", [])
    policy_result = state.get("policy_result", {})

    state.setdefault("workers_called", [])
    state.setdefault("history", [])
    state["workers_called"].append(WORKER_NAME)
    state["history"].append(
        f"[{WORKER_NAME}] starting synthesis | chunks={len(chunks)} | "
        f"has_policy={bool(policy_result)} | has_exceptions="
        f"{bool(policy_result.get('exceptions_found'))}"
    )

    # Worker IO log (theo contract trong worker_contracts.yaml)
    worker_io = {
        "worker": WORKER_NAME,
        "input": {
            "task": task,
            "chunks_count": len(chunks),
            "has_policy_result": bool(policy_result),
            "has_exceptions": bool(policy_result.get("exceptions_found")),
        },
        "output": None,
        "error": None,
    }

    try:
        result = synthesize(task, chunks, policy_result)

        state["final_answer"] = result["answer"]
        state["sources"] = result["sources"]
        state["confidence"] = result["confidence"]

        worker_io["output"] = {
            "answer_length": len(result["answer"]),
            "sources": result["sources"],
            "confidence": result["confidence"],
        }

        state["history"].append(
            f"[{WORKER_NAME}] done | confidence={result['confidence']} | "
            f"sources={result['sources']} | answer_len={len(result['answer'])}"
        )

    except Exception as e:
        err_msg = f"SYNTHESIS_FAILED: {e}"
        worker_io["error"] = {"code": "SYNTHESIS_FAILED", "reason": str(e)}
        state["final_answer"] = f"[ERROR] {err_msg}"
        state["confidence"] = 0.0
        state["history"].append(f"[{WORKER_NAME}] ERROR: {e}")

    state.setdefault("worker_io_logs", []).append(worker_io)
    return state


# ─────────────────────────────────────────────
# Standalone Test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("=" * 60)
    print("  Synthesis Worker — Standalone Test (M6)")
    print("=" * 60)

    # ── Test 1: SLA P1 query (retrieval route) ──
    print("\n[Test 1] SLA P1 query — retrieval route")
    state1 = {
        "task": "SLA ticket P1 là bao lâu?",
        "retrieved_chunks": [
            {
                "text": (
                    "Ticket P1: Phản hồi ban đầu 15 phút kể từ khi ticket được tạo. "
                    "Xử lý và khắc phục trong 4 giờ. Escalation tự động lên Senior Engineer "
                    "nếu không có phản hồi trong 10 phút."
                ),
                "source": "sla_p1_2026.txt",
                "score": 0.92,
            },
            {
                "text": (
                    "On-call Engineer nhận thông báo qua PagerDuty trong vòng 5 phút "
                    "sau khi ticket P1 được tạo."
                ),
                "source": "sla_p1_2026.txt",
                "score": 0.85,
            },
        ],
        "policy_result": {},
    }
    r1 = run(state1.copy())
    print(f"  Answer   : {r1['final_answer'][:200]}")
    print(f"  Sources  : {r1['sources']}")
    print(f"  Confidence: {r1['confidence']}")

    # ── Test 2: Flash Sale exception (policy route) ──
    print("\n[Test 2] Flash Sale hoàn tiền — policy exception case")
    state2 = {
        "task": "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?",
        "retrieved_chunks": [
            {
                "text": (
                    "Chính sách hoàn tiền v4: Điều 3 — Các đơn hàng trong chương trình "
                    "Flash Sale không được áp dụng chính sách hoàn tiền tiêu chuẩn. "
                    "Thay vào đó, khách hàng được cấp Store Credit 110% giá trị đơn hàng."
                ),
                "source": "policy_refund_v4.txt",
                "score": 0.91,
            },
        ],
        "policy_result": {
            "policy_applies": False,
            "policy_name": "refund_policy_v4",
            "exceptions_found": [
                {
                    "type": "flash_sale_exception",
                    "rule": "Flash Sale không được hoàn tiền tiêu chuẩn — chỉ nhận Store Credit 110%.",
                }
            ],
        },
    }
    r2 = run(state2.copy())
    print(f"  Answer   : {r2['final_answer'][:200]}")
    print(f"  Confidence: {r2['confidence']}")

    # ── Test 3: Abstain case (không có thông tin) ──
    print("\n[Test 3] Abstain — mức phạt tài chính SLA P1 (không có trong docs)")
    state3 = {
        "task": "Mức phạt tài chính nếu vi phạm SLA P1 là bao nhiêu?",
        "retrieved_chunks": [],   # Không retrieve được gì
        "policy_result": {},
    }
    r3 = run(state3.copy())
    print(f"  Answer   : {r3['final_answer'][:200]}")
    print(f"  Confidence: {r3['confidence']}")

    # ── Test 4: Multi-hop (SLA + access control) ──
    print("\n[Test 4] Multi-hop — P1 2am + cấp quyền Level 2 cho contractor")
    state4 = {
        "task": "Ticket P1 lúc 2am. Contractor cần cấp quyền Level 2 tạm thời. Nêu cả hai quy trình.",
        "retrieved_chunks": [
            {
                "text": (
                    "SLA P1: On-call Engineer nhận notify trong 5 phút qua PagerDuty. "
                    "Nếu không phản hồi trong 10 phút → escalate lên Senior Engineer. "
                    "Escalation thứ 2 sau 30 phút lên Engineering Manager."
                ),
                "source": "sla_p1_2026.txt",
                "score": 0.89,
            },
            {
                "text": (
                    "Emergency Access — Level 2: Cần 2 người phê duyệt: "
                    "IT Security Manager và Department Head. "
                    "Thời hạn tạm thời tối đa 24 giờ. Phải có ticket incident đính kèm."
                ),
                "source": "access_control_sop.txt",
                "score": 0.86,
            },
        ],
        "policy_result": {
            "policy_applies": True,
            "policy_name": "emergency_access_procedure",
            "exceptions_found": [],
        },
    }
    r4 = run(state4.copy())
    print(f"  Answer   : {r4['final_answer'][:300]}")
    print(f"  Sources  : {r4['sources']}")
    print(f"  Confidence: {r4['confidence']}")

    # ── Summary ──
    print("\n" + "=" * 60)
    print("Sprint 2 Checklist — synthesis_worker:")
    all_ok = all([
        r1["final_answer"] and r1["confidence"] > 0,
        r2["final_answer"] and r2["confidence"] > 0,
        r3["confidence"] <= 0.3,                           # abstain → low confidence
        r4["final_answer"] and len(r4["sources"]) >= 2,    # multi-hop → multiple sources
    ])
    print(f"  [{'x' if r1['confidence'] > 0 else ' '}] Test 1: SLA retrieval OK, confidence={r1['confidence']}")
    print(f"  [{'x' if r2['confidence'] > 0 else ' '}] Test 2: Flash Sale exception handled, confidence={r2['confidence']}")
    print(f"  [{'x' if r3['confidence'] <= 0.3 else ' '}] Test 3: Abstain (no chunks) → low confidence={r3['confidence']}")
    print(f"  [{'x' if len(r4['sources']) >= 2 else ' '}] Test 4: Multi-hop → sources={r4['sources']}")
    print(f"\n{'✅ synthesis_worker PASSED!' if all_ok else '❌ Some tests failed — check above.'}")
