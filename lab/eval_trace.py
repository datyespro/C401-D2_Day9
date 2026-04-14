"""
eval_trace.py - Trace Evaluation & Comparison
Sprint 4: Chay pipeline voi test questions, phan tich trace, so sanh single vs multi.

Chay:
    python eval_trace.py                  # Chay 15 test questions
    python eval_trace.py --grading        # Chay grading questions (sau 17:00)
    python eval_trace.py --analyze        # Phan tich trace da co
    python eval_trace.py --compare        # So sanh single vs multi

Outputs:
    artifacts/traces/           - trace cua tung cau hoi (.json)
    artifacts/grading_run.jsonl - log cau hoi cham diem
    artifacts/eval_report.json  - bao cao tong ket
"""

import json
import os
import sys
import argparse
from datetime import datetime
from typing import Optional

# Fix Windows terminal encoding (cp1252 -> utf-8)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Import graph
sys.path.insert(0, os.path.dirname(__file__))
from graph import run_graph, save_trace


# ─────────────────────────────────────────────
# 1. Run Pipeline on Test Questions
# ─────────────────────────────────────────────

def run_test_questions(questions_file: str = "data/test_questions.json") -> list:
    """
    Chạy pipeline với danh sách câu hỏi, lưu trace từng câu.

    Returns:
        list of question result dicts
    """
    if not os.path.exists(questions_file):
        print(f"❌ File {questions_file} không tồn tại.")
        return []

    with open(questions_file, encoding="utf-8") as f:
        questions = json.load(f)

    print(f"\n[INFO] Running {len(questions)} test questions from {questions_file}")
    print("=" * 60)

    results = []
    for i, q in enumerate(questions, 1):
        question_text = q["question"]
        q_id = q.get("id", f"q{i:02d}")

        print(f"[{i:02d}/{len(questions)}] {q_id}: {question_text[:65]}...")

        try:
            result = run_graph(question_text)
            result["question_id"] = q_id

            # Save individual trace — pass q_id to avoid filename collision
            trace_file = save_trace(result, "artifacts/traces", question_id=q_id)

            # Tính routing accuracy cho câu này
            expected_route = q.get("expected_route", "")
            actual_route = result.get("supervisor_route", "")
            route_correct = (expected_route == actual_route) if expected_route else None

            # Tính source hit
            expected_sources = set(q.get("expected_sources", []))
            actual_sources = set(result.get("retrieved_sources", []))
            source_hit = bool(expected_sources & actual_sources) if expected_sources else None

            status_icon = "OK" if route_correct else ("??" if route_correct is None else "XX")
            print(f"  {status_icon} route={actual_route} (expected={expected_route or 'any'}), "
                  f"conf={result.get('confidence', 0):.2f}, "
                  f"{result.get('latency_ms', 0)}ms")
            if not route_correct and expected_route:
                print(f"    [WARN] Routing mismatch! expected={expected_route}, got={actual_route}")

            results.append({
                "id": q_id,
                "question": question_text,
                "expected_answer": q.get("expected_answer", ""),
                "expected_sources": list(expected_sources),
                "expected_route": expected_route,
                "difficulty": q.get("difficulty", "unknown"),
                "category": q.get("category", "unknown"),
                "test_type": q.get("test_type", "unknown"),
                "result": result,
                # Evaluation fields
                "route_correct": route_correct,
                "source_hit": source_hit,
            })

        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            results.append({
                "id": q_id,
                "question": question_text,
                "error": str(e),
                "result": None,
                "route_correct": False,
                "source_hit": False,
            })

    succeeded = sum(1 for r in results if r.get("result"))
    print(f"\n✅ Done. {succeeded} / {len(results)} succeeded.")
    return results


# ─────────────────────────────────────────────
# 2. Run Grading Questions (Sprint 4)
# ─────────────────────────────────────────────

def run_grading_questions(questions_file: str = "data/grading_questions.json") -> str:
    """
    Chạy pipeline với grading questions và lưu JSONL log.
    Dùng cho chấm điểm nhóm (chạy sau khi grading_questions.json được public lúc 17:00).

    Returns:
        path tới grading_run.jsonl
    """
    if not os.path.exists(questions_file):
        print(f"❌ {questions_file} chưa được public (sau 17:00 mới có).")
        return ""

    with open(questions_file, encoding="utf-8") as f:
        questions = json.load(f)

    os.makedirs("artifacts", exist_ok=True)
    output_file = "artifacts/grading_run.jsonl"

    print(f"\n[GRADING] Running GRADING questions -- {len(questions)} cau")
    print(f"   Output → {output_file}")
    print("=" * 60)

    with open(output_file, "w", encoding="utf-8") as out:
        for i, q in enumerate(questions, 1):
            q_id = q.get("id", f"gq{i:02d}")
            question_text = q["question"]
            print(f"[{i:02d}/{len(questions)}] {q_id}: {question_text[:65]}...")

            try:
                result = run_graph(question_text)
                record = {
                    "id": q_id,
                    "question": question_text,
                    "answer": result.get("final_answer", "PIPELINE_ERROR: no answer"),
                    "sources": result.get("retrieved_sources", []),
                    "supervisor_route": result.get("supervisor_route", ""),
                    "route_reason": result.get("route_reason", ""),
                    "workers_called": result.get("workers_called", []),
                    "mcp_tools_used": [
                        t.get("tool") if isinstance(t, dict) else t
                        for t in result.get("mcp_tools_used", [])
                    ],
                    "confidence": result.get("confidence", 0.0),
                    "hitl_triggered": result.get("hitl_triggered", False),
                    "latency_ms": result.get("latency_ms"),
                    "timestamp": datetime.now().isoformat(),
                }
                print(f"  ✓ route={record['supervisor_route']}, conf={record['confidence']:.2f}")
            except Exception as e:
                record = {
                    "id": q_id,
                    "question": question_text,
                    "answer": f"PIPELINE_ERROR: {e}",
                    "sources": [],
                    "supervisor_route": "error",
                    "route_reason": str(e),
                    "workers_called": [],
                    "mcp_tools_used": [],
                    "confidence": 0.0,
                    "hitl_triggered": False,
                    "latency_ms": None,
                    "timestamp": datetime.now().isoformat(),
                }
                print(f"  ✗ ERROR: {e}")

            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\n✅ Grading log saved → {output_file}")
    return output_file


# ─────────────────────────────────────────────
# 3. Analyze Traces
# ─────────────────────────────────────────────

def analyze_traces(traces_dir: str = "artifacts/traces") -> dict:
    """
    Đọc tất cả trace files và tính metrics tổng hợp.

    Metrics:
    - total_traces: tổng số trace
    - routing_distribution: % câu đi vào mỗi worker
    - avg_confidence: confidence trung bình
    - avg_latency_ms: latency trung bình
    - mcp_usage_rate: % câu có MCP tool call
    - hitl_rate: % câu trigger HITL
    - top_sources: các tài liệu được dùng nhiều nhất

    Returns:
        dict of metrics
    """
    if not os.path.exists(traces_dir):
        print(f"⚠️  {traces_dir} không tồn tại. Chạy run_test_questions() trước.")
        return {}

    trace_files = [f for f in os.listdir(traces_dir) if f.endswith(".json")]
    if not trace_files:
        print(f"⚠️  Không có trace files trong {traces_dir}.")
        return {}

    traces = []
    for fname in trace_files:
        fpath = os.path.join(traces_dir, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                traces.append(json.load(f))
        except Exception as e:
            print(f"⚠️  Không đọc được {fname}: {e}")

    if not traces:
        return {}

    # Compute metrics
    routing_counts = {}
    confidences = []
    latencies = []
    mcp_calls = 0
    hitl_triggers = 0
    source_counts = {}

    for t in traces:
        # Routing distribution
        route = t.get("supervisor_route", "unknown")
        routing_counts[route] = routing_counts.get(route, 0) + 1

        # Confidence
        conf = t.get("confidence")
        if conf is not None and conf > 0:
            confidences.append(conf)

        # Latency
        lat = t.get("latency_ms")
        if lat is not None and lat > 0:
            latencies.append(lat)

        # MCP usage
        mcp_used = t.get("mcp_tools_used", [])
        if mcp_used:
            mcp_calls += 1

        # HITL
        if t.get("hitl_triggered"):
            hitl_triggers += 1

        # Source usage
        for src in t.get("retrieved_sources", []):
            source_counts[src] = source_counts.get(src, 0) + 1

    total = len(traces)

    def pct(count):
        return f"{count}/{total} ({100 * count // total}%)" if total else "0/0 (0%)"

    metrics = {
        "total_traces": total,
        "routing_distribution": {
            k: pct(v) for k, v in sorted(routing_counts.items(), key=lambda x: -x[1])
        },
        "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0.0,
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
        "mcp_usage_rate": pct(mcp_calls),
        "hitl_rate": pct(hitl_triggers),
        "top_sources": sorted(source_counts.items(), key=lambda x: -x[1])[:5],
    }

    return metrics


# ─────────────────────────────────────────────
# 4. Evaluate Routing Accuracy
# ─────────────────────────────────────────────

def evaluate_routing_accuracy(results: list) -> dict:
    """
    Tính routing accuracy và source hit rate bằng cách
    so sánh kết quả thực tế với expected trong test_questions.json.

    Args:
        results: list trả về từ run_test_questions()

    Returns:
        dict of accuracy metrics
    """
    if not results:
        return {}

    # Chỉ evaluate những câu có expected_route
    route_eval = [r for r in results if r.get("expected_route") and r.get("route_correct") is not None]
    source_eval = [r for r in results if r.get("expected_sources") and r.get("source_hit") is not None]

    route_correct = sum(1 for r in route_eval if r.get("route_correct"))
    source_hit = sum(1 for r in source_eval if r.get("source_hit"))

    # Phân tích theo độ khó
    by_difficulty = {}
    for r in results:
        diff = r.get("difficulty", "unknown")
        if diff not in by_difficulty:
            by_difficulty[diff] = {"total": 0, "route_correct": 0}
        by_difficulty[diff]["total"] += 1
        if r.get("route_correct"):
            by_difficulty[diff]["route_correct"] += 1

    # Phân tích các câu routing sai
    routing_mistakes = [
        {
            "id": r["id"],
            "question": r["question"][:70] + "...",
            "expected": r.get("expected_route"),
            "actual": r.get("result", {}).get("supervisor_route", "error") if r.get("result") else "error",
            "reason": r.get("result", {}).get("route_reason", "") if r.get("result") else "",
        }
        for r in route_eval if not r.get("route_correct")
    ]

    accuracy_report = {
        "routing_accuracy": {
            "correct": route_correct,
            "total_evaluated": len(route_eval),
            "accuracy_pct": round(100 * route_correct / len(route_eval), 1) if route_eval else 0,
        },
        "source_hit_rate": {
            "hit": source_hit,
            "total_evaluated": len(source_eval),
            "hit_pct": round(100 * source_hit / len(source_eval), 1) if source_eval else 0,
        },
        "by_difficulty": {
            diff: {
                "total": v["total"],
                "route_correct": v["route_correct"],
                "accuracy_pct": round(100 * v["route_correct"] / v["total"], 1) if v["total"] else 0,
            }
            for diff, v in by_difficulty.items()
        },
        "routing_mistakes": routing_mistakes,
    }

    return accuracy_report


# ─────────────────────────────────────────────
# 5. Compare Single vs Multi Agent
# ─────────────────────────────────────────────

def compare_single_vs_multi(
    multi_metrics: dict,
    accuracy_report: dict,
    day08_results_file: Optional[str] = None,
) -> dict:
    """
    So sánh Day 08 (single agent RAG) vs Day 09 (multi-agent).

    Returns:
        dict của comparison metrics
    """
    # ── Baseline Day 08: điền số liệu thực tế từ lab Day 08 ──
    # TODO: Cập nhật các giá trị này từ kết quả eval.py của Day 08
    day08_baseline = {
        "architecture": "Single RAG pipeline (retrieve → generate)",
        "avg_confidence": 0.0,       # TODO: Điền từ Day 08 eval.py
        "avg_latency_ms": 0,         # TODO: Điền từ Day 08
        "routing_visibility": "Không có — một pipeline đơn, không rõ bước nào sai",
        "worker_testability": "Không thể test từng bước độc lập",
        "mcp_support": "Không có",
        "debuggability": "Thấp — lỗi không rõ ở retrieval hay generation",
    }

    if day08_results_file and os.path.exists(day08_results_file):
        with open(day08_results_file, encoding="utf-8") as f:
            day08_baseline.update(json.load(f))

    # ── Metrics Day 09 (từ traces thực tế) ──
    day09_metrics = {
        "architecture": "Supervisor-Worker Multi-Agent Graph",
        "avg_confidence": multi_metrics.get("avg_confidence", 0.0),
        "avg_latency_ms": multi_metrics.get("avg_latency_ms", 0),
        "routing_accuracy_pct": accuracy_report.get("routing_accuracy", {}).get("accuracy_pct", 0),
        "source_hit_rate_pct": accuracy_report.get("source_hit_rate", {}).get("hit_pct", 0),
        "routing_distribution": multi_metrics.get("routing_distribution", {}),
        "mcp_usage_rate": multi_metrics.get("mcp_usage_rate", "0%"),
        "hitl_rate": multi_metrics.get("hitl_rate", "0%"),
        "routing_visibility": "Có — mỗi câu có route_reason và worker_io_logs",
        "worker_testability": "Có — mỗi worker test được độc lập",
        "mcp_support": "Có — gọi external capability qua MCP interface",
        "debuggability": "Cao — trace từng bước, Routing Error Tree",
    }

    # ── Tính delta ──
    def delta_str(val09, val08, unit=""):
        if not val08 or not val09:
            return "N/A (baseline chưa có)"
        delta = val09 - val08
        sign = "+" if delta > 0 else ""
        return f"{sign}{delta:.1f}{unit}"

    comparison = {
        "generated_at": datetime.now().isoformat(),
        "day08_single_agent": day08_baseline,
        "day09_multi_agent": day09_metrics,
        "deltas": {
            "latency_delta": delta_str(
                day09_metrics.get("avg_latency_ms", 0),
                day08_baseline.get("avg_latency_ms", 0),
                "ms"
            ),
            "confidence_delta": delta_str(
                day09_metrics.get("avg_confidence", 0),
                day08_baseline.get("avg_confidence", 0),
            ),
        },
        "qualitative_analysis": {
            "routing_visibility": "[+] Day 09 co route_reason -> de debug hon Day 08",
            "debuggability": "[+] Multi-agent: test tung worker doc lap. Single-agent: khong the.",
            "mcp_extensibility": "[+] Day 09 extend capability qua MCP khong can sua core pipeline.",
            "latency_tradeoff": "[!] Multi-agent co overhead do goi nhieu workers -- can danh doi vs accuracy.",
            "complexity": "[!] Multi-agent phuc tap hon Single-agent -- can routing logic chinh xac.",
        },
        "accuracy_breakdown": accuracy_report,
    }

    return comparison


# ─────────────────────────────────────────────
# 6. Save Eval Report
# ─────────────────────────────────────────────

def save_eval_report(comparison: dict, accuracy_report: dict) -> str:
    """Lưu báo cáo eval tổng kết ra file JSON."""
    os.makedirs("artifacts", exist_ok=True)
    output_file = "artifacts/eval_report.json"
    report = {**comparison, "accuracy_report": accuracy_report}
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return output_file


# ─────────────────────────────────────────────
# 7. Pretty Print
# ─────────────────────────────────────────────

def print_metrics(metrics: dict, title: str = "📊 Trace Analysis"):
    """Print metrics đẹp."""
    if not metrics:
        print("  (không có dữ liệu)")
        return
    print(f"\n{title}:")
    print("-" * 50)
    for k, v in metrics.items():
        if isinstance(v, list):
            print(f"  {k}:")
            for item in v:
                print(f"    • {item}")
        elif isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"    {kk}: {vv}")
        else:
            print(f"  {k}: {v}")


def print_accuracy_report(report: dict):
    """Print routing accuracy report đẹp."""
    if not report:
        return

    ra = report.get("routing_accuracy", {})
    sh = report.get("source_hit_rate", {})
    print("\n[ACCURACY] Routing & Source Accuracy:")
    print("-" * 50)
    print(f"  Routing Accuracy : {ra.get('correct')}/{ra.get('total_evaluated')} "
          f"({ra.get('accuracy_pct')}%)")
    print(f"  Source Hit Rate  : {sh.get('hit')}/{sh.get('total_evaluated')} "
          f"({sh.get('hit_pct')}%)")

    by_diff = report.get("by_difficulty", {})
    if by_diff:
        print("  By Difficulty:")
        for diff in ["easy", "medium", "hard"]:
            if diff in by_diff:
                d = by_diff[diff]
                print(f"    {diff:8s}: {d['route_correct']}/{d['total']} ({d['accuracy_pct']}%)")

    mistakes = report.get("routing_mistakes", [])
    if mistakes:
        print(f"\n  [WARN] Routing Mistakes ({len(mistakes)} cau):")
        for m in mistakes:
            print(f"    [{m['id']}] expected={m['expected']} → got={m['actual']}")
            print(f"           reason: {m['reason'][:80]}")


# ─────────────────────────────────────────────
# 8. CLI Entry Point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Day 09 Lab — Trace Evaluation")
    parser.add_argument("--grading", action="store_true", help="Run grading questions")
    parser.add_argument("--analyze", action="store_true", help="Analyze existing traces")
    parser.add_argument("--compare", action="store_true", help="Compare single vs multi")
    parser.add_argument("--test-file", default="data/test_questions.json",
                        help="Test questions file")
    parser.add_argument("--day08-baseline", default=None,
                        help="Path to Day 08 baseline JSON file")
    args = parser.parse_args()

    if args.grading:
        # Chạy grading questions (sau 17:00)
        log_file = run_grading_questions()
        if log_file:
            print(f"\n✅ Grading log: {log_file}")
            print("   Nộp file này trước 18:00!")

    elif args.analyze:
        # Phân tích traces đã có
        metrics = analyze_traces()
        print_metrics(metrics)

    elif args.compare:
        # So sánh single vs multi dựa trên traces đã có
        metrics = analyze_traces()
        comparison = compare_single_vs_multi(metrics, {}, args.day08_baseline)
        report_file = save_eval_report(comparison, {})
        print(f"\n[OK] Comparison report saved -> {report_file}")
        print("\n=== Day 08 vs Day 09 ===")
        for k, v in comparison.get("qualitative_analysis", {}).items():
            print(f"  {k}: {v}")

    else:
        # Default: chạy test questions + đánh giá đầy đủ
        print("=" * 60)
        print("Day 09 Lab — Sprint 4: Full Evaluation")
        print("=" * 60)

        # Bước 1: Chạy pipeline
        results = run_test_questions(args.test_file)

        # Bước 2: Phân tích trace
        metrics = analyze_traces()
        print_metrics(metrics)

        # Bước 3: Tính routing accuracy
        accuracy_report = evaluate_routing_accuracy(results)
        print_accuracy_report(accuracy_report)

        # Bước 4: So sánh Day 08 vs Day 09
        comparison = compare_single_vs_multi(metrics, accuracy_report, args.day08_baseline)
        report_file = save_eval_report(comparison, accuracy_report)

        print(f"\n[OK] Eval report -> {report_file}")
        print("\n[DONE] Sprint 4 complete!")
        print("   Next: Gui eval_report.json cho Thanh vien 6 de viet so sanh.")
        print("   Next: Luc 17:00 chay: python eval_trace.py --grading")
