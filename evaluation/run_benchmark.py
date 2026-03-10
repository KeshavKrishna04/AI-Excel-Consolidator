from __future__ import annotations

"""
Single-entry evaluation script.

Usage (from project root):

    python evaluation/run_benchmark.py --workbook outputs/consolidated_output.xlsx

This will:
1) Export the Q&A LangGraph workflow as PNG (evaluation/langgraph_pipeline.png)
2) Regenerate evaluation/question_bank.json for the given workbook
3) Run the benchmark (one call per question)
4) Overwrite:
   - evaluation/benchmark_results.csv
   - evaluation/performance_report.md
"""

import argparse
import base64
import csv
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from graph.qa_graph import build_qa_graph  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers: LangGraph pipeline PNG export
# ---------------------------------------------------------------------------

def _render_mermaid_png_via_mermaid_ink(mermaid: str) -> bytes:
    """Render Mermaid graph definition into PNG via Mermaid.ink."""
    b64 = base64.urlsafe_b64encode(mermaid.encode("utf-8")).decode("ascii").rstrip("=")
    url = f"https://mermaid.ink/img/{b64}"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content


def export_pipeline_png(png_path: Path) -> None:
    """Export the Q&A LangGraph workflow as a PNG image."""
    png_path.parent.mkdir(parents=True, exist_ok=True)

    graph = build_qa_graph()
    drawable = graph.get_graph()

    mermaid = drawable.draw_mermaid()

    # Try native PNG export first, then fall back to Mermaid.ink.
    try:
        png_bytes = drawable.draw_png()
    except Exception:
        png_bytes = _render_mermaid_png_via_mermaid_ink(mermaid)

    png_path.write_bytes(png_bytes)


# ---------------------------------------------------------------------------
# Helpers: Excel inspection utilities (collapsed from utils_excel.py)
# ---------------------------------------------------------------------------

def _contains_any(haystack: str, needles: Iterable[str]) -> bool:
    h = haystack.lower()
    return any(n.lower() in h for n in needles)


def load_workbook(path: str) -> Dict[str, pd.DataFrame]:
    return pd.read_excel(path, sheet_name=None)


def find_sheet(sheets: Dict[str, pd.DataFrame], keyword: str) -> Optional[str]:
    key = keyword.lower()
    for name in sheets.keys():
        if key in str(name).lower():
            return str(name)
    return None


def guess_dim_columns(df: pd.DataFrame) -> Dict[str, str]:
    """Best-effort mapping of semantic dimensions to actual column names."""
    dims: Dict[str, str] = {}
    for col in df.columns:
        c = str(col).strip()
        cl = c.lower()
        if "brand" in cl and "brand" not in dims:
            dims["brand"] = c
        elif cl == "state" and "state" not in dims:
            dims["state"] = c
        elif cl == "city" and "city" not in dims:
            dims["city"] = c
        elif cl == "region" and "region" not in dims:
            dims["region"] = c
        elif cl == "channel" and "channel" not in dims:
            dims["channel"] = c
        elif _contains_any(cl, ["pack_type", "packtype"]) and "pack_type" not in dims:
            dims["pack_type"] = c
        elif cl == "category" and "category" not in dims:
            dims["category"] = c
        elif _contains_any(cl, ["promotion_type", "promo", "promotion"]) and "promotion_type" not in dims:
            dims["promotion_type"] = c
    return dims


def guess_metric_columns(df: pd.DataFrame) -> Dict[str, str]:
    """Best-effort mapping of metric semantics to actual numeric columns."""
    metrics: Dict[str, str] = {}
    for col in df.columns:
        c = str(col).strip()
        cl = c.lower()
        series = pd.to_numeric(df[col], errors="coerce")
        if not series.notna().any():
            continue

        if "quantity" not in metrics and _contains_any(cl, ["qty", "quantity", "volume", "cases", "units"]):
            metrics["quantity"] = c
        if "value" not in metrics and _contains_any(cl, ["net_sales", "nsv", "sales_value", "value", "revenue"]):
            metrics["value"] = c
        if "discount" not in metrics and _contains_any(cl, ["disc", "discount"]):
            metrics["discount"] = c
        if "margin" not in metrics and "margin" in cl:
            metrics["margin"] = c

    return metrics


def safe_unique_count(df: pd.DataFrame, col: str) -> int:
    if col not in df.columns:
        return 0
    return int(df[col].dropna().nunique())


def top_value_by_count(df: pd.DataFrame, col: str) -> Optional[tuple[str, int]]:
    if col not in df.columns:
        return None
    vc = df[col].dropna().astype(str).value_counts()
    if vc.empty:
        return None
    value = str(vc.index[0])
    count = int(vc.iloc[0])
    return value, count


def count_occurrences(df: pd.DataFrame, col: str, value: str) -> int:
    if col not in df.columns:
        return 0
    return int((df[col].astype(str).str.lower() == value.lower()).sum())


def sum_metric(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns:
        return 0.0
    s = pd.to_numeric(df[col], errors="coerce")
    return float(s.sum(skipna=True))


def mean_metric(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns:
        return 0.0
    s = pd.to_numeric(df[col], errors="coerce")
    return float(s.mean(skipna=True))


def median_metric(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns:
        return 0.0
    s = pd.to_numeric(df[col], errors="coerce")
    return float(s.median(skipna=True))


def max_metric(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns:
        return 0.0
    s = pd.to_numeric(df[col], errors="coerce")
    return float(s.max(skipna=True))


def top_n_by_sum(df: pd.DataFrame, group_col: str, metric_col: str, n: int) -> List[tuple[str, float]]:
    if group_col not in df.columns or metric_col not in df.columns:
        return []
    grouped = df.groupby(group_col, dropna=True)[metric_col].apply(
        lambda s: pd.to_numeric(s, errors="coerce").sum()
    )
    grouped = grouped.sort_values(ascending=False).head(n)
    return [(str(idx), float(val)) for idx, val in grouped.items()]


def top_n_by_count(df: pd.DataFrame, group_col: str, n: int) -> List[tuple[str, int]]:
    if group_col not in df.columns:
        return []
    vc = df[group_col].dropna().astype(str).value_counts().head(n)
    return [(str(idx), int(val)) for idx, val in vc.items()]


# ---------------------------------------------------------------------------
# Question bank: build 20 questions with real expected answers
# ---------------------------------------------------------------------------

def build_question_bank(workbook_path: str) -> List[Dict[str, Any]]:
    sheets = load_workbook(workbook_path)
    sales_name = find_sheet(sheets, "consolidated_sales") or find_sheet(sheets, "sales")
    nielsen_name = find_sheet(sheets, "consolidated_nielsen") or find_sheet(sheets, "nielsen")

    if not sales_name:
        raise ValueError("Cannot build question bank: no Sales sheet found in workbook.")

    sales_df = sheets[sales_name]
    dims = guess_dim_columns(sales_df)
    metrics = guess_metric_columns(sales_df)

    q: List[Dict[str, Any]] = []

    # 1) Total records
    q.append(
        {
            "question": f"How many total records are present in the {sales_name} sheet?",
            "expected_answer": str(int(sales_df.shape[0])),
        }
    )

    # 2) Rows/cols
    q.append(
        {
            "question": f"How many rows and columns are there in the {sales_name} sheet?",
            "expected_answer": f"{int(sales_df.shape[0])} rows, {int(sales_df.shape[1])} columns",
        }
    )

    # 3) Unique brands
    if "brand" in dims:
        q.append(
            {
                "question": "How many unique brands appear in the sales data?",
                "expected_answer": str(safe_unique_count(sales_df, dims["brand"])),
            }
        )

    # 4) Pack type uniques (names list)
    if "pack_type" in dims:
        unique_pack_types = sorted(
            sales_df[dims["pack_type"]].dropna().astype(str).unique().tolist()
        )
        q.append(
            {
                "question": "What are the different pack types available in the dataset?",
                "expected_answer": ", ".join(unique_pack_types),
            }
        )

    # 5) State highest record count
    if "state" in dims:
        top_state = top_value_by_count(sales_df, dims["state"])
        if top_state:
            q.append(
                {
                    "question": "Which state has the highest number of sales records?",
                    "expected_answer": f"{top_state[0]}",
                }
            )

    # 6) City most frequent
    if "city" in dims:
        top_city = top_value_by_count(sales_df, dims["city"])
        if top_city:
            q.append(
                {
                    "question": "Which city appears most frequently in the sales data?",
                    "expected_answer": f"{top_city[0]}",
                }
            )

    # 7) Channel most transactions
    if "channel" in dims:
        top_channel = top_value_by_count(sales_df, dims["channel"])
        if top_channel:
            q.append(
                {
                    "question": "Which channel has the most transactions?",
                    "expected_answer": f"{top_channel[0]}",
                }
            )

    # 8) Top 5 brands by frequency
    if "brand" in dims:
        top5 = top_n_by_count(sales_df, dims["brand"], 5)
        expected = ", ".join([f"{b} ({c})" for b, c in top5])
        q.append(
            {
                "question": "What are the top 5 brands by frequency in the dataset?",
                "expected_answer": expected,
            }
        )

    # 9) Tetrapack occurrences
    if "pack_type" in dims:
        tetrapack_count = count_occurrences(sales_df, dims["pack_type"], "Tetrapack")
        q.append(
            {
                "question": "How many times does Tetrapack appear in the pack_type column?",
                "expected_answer": str(tetrapack_count),
            }
        )

    # 10) Total net sales value
    if "value" in metrics:
        total_value = sum_metric(sales_df, metrics["value"])
        q.append(
            {
                "question": "What is the total net sales value across all transactions?",
                "expected_answer": f"{total_value:.2f}",
            }
        )

    # 11) Average quantity
    if "quantity" in metrics:
        avg_qty = mean_metric(sales_df, metrics["quantity"])
        q.append(
            {
                "question": "What is the average sales quantity per transaction?",
                "expected_answer": f"{avg_qty:.4f}",
            }
        )

    # 12) Median quantity
    if "quantity" in metrics:
        med_qty = median_metric(sales_df, metrics["quantity"])
        q.append(
            {
                "question": "What is the median sales quantity per record?",
                "expected_answer": f"{med_qty:.4f}",
            }
        )

    # 13) Max quantity
    if "quantity" in metrics:
        mx = max_metric(sales_df, metrics["quantity"])
        q.append(
            {
                "question": "What is the maximum sales quantity recorded in a single transaction?",
                "expected_answer": f"{mx:.4f}",
            }
        )

    # 14) Brand with highest total quantity
    if "brand" in dims and "quantity" in metrics:
        top_brand_qty = top_n_by_sum(sales_df, dims["brand"], metrics["quantity"], 1)
        if top_brand_qty:
            b, v = top_brand_qty[0]
            q.append(
                {
                    "question": "Which brand has the highest total sales quantity?",
                    "expected_answer": f"{b} ({v:.2f})",
                }
            )

    # 15) State highest total sales value
    if "state" in dims and "value" in metrics:
        top_state_value = top_n_by_sum(sales_df, dims["state"], metrics["value"], 1)
        if top_state_value:
            s, v = top_state_value[0]
            q.append(
                {
                    "question": "Which state contributes the highest total sales value?",
                    "expected_answer": f"{s} ({v:.2f})",
                }
            )

    # 16) Top 5 brands by value
    if "brand" in dims and "value" in metrics:
        top5_val = top_n_by_sum(sales_df, dims["brand"], metrics["value"], 5)
        expected = ", ".join([f"{b} ({v:.2f})" for b, v in top5_val])
        q.append(
            {
                "question": "List the top 5 brands by net sales value.",
                "expected_answer": expected,
            }
        )

    # 17) Top 3 pack types by quantity
    if "pack_type" in dims and "quantity" in metrics:
        top3_pack = top_n_by_sum(sales_df, dims["pack_type"], metrics["quantity"], 3)
        expected = ", ".join([f"{p} ({v:.2f})" for p, v in top3_pack])
        q.append(
            {
                "question": "What are the top 3 pack types by sales quantity?",
                "expected_answer": expected,
            }
        )

    # 18) Which channel generates the highest revenue
    if "channel" in dims and "value" in metrics:
        top_channel_value = top_n_by_sum(sales_df, dims["channel"], metrics["value"], 1)
        if top_channel_value:
            ch, v = top_channel_value[0]
            q.append(
                {
                    "question": "Which channel generates the highest revenue?",
                    "expected_answer": f"{ch} ({v:.2f})",
                }
            )

    # 19) Cross-sheet Sales vs Nielsen (if possible)
    if nielsen_name and "brand" in dims and "value" in metrics:
        nielsen_df = sheets[nielsen_name]
        n_brand = None
        for col in nielsen_df.columns:
            if "brand" in str(col).lower():
                n_brand = str(col)
                break
        n_value = None
        for col in nielsen_df.columns:
            cl = str(col).lower()
            if any(k in cl for k in ["brand_sales", "sales_inr", "sales_value", "value", "revenue"]):
                series = pd.to_numeric(nielsen_df[col], errors="coerce")
                if series.notna().any():
                    n_value = str(col)
                    break

        if n_brand and n_value:
            sales_totals = (
                sales_df.groupby(dims["brand"], dropna=True)[metrics["value"]]
                .apply(lambda s: pd.to_numeric(s, errors="coerce").sum())
            )
            nielsen_totals = (
                nielsen_df.groupby(n_brand, dropna=True)[n_value]
                .apply(lambda s: pd.to_numeric(s, errors="coerce").sum())
            )
            common = set(map(str, sales_totals.index)).intersection(set(map(str, nielsen_totals.index)))
            if common:
                diffs = []
                for brand in common:
                    diff = float(sales_totals.loc[brand]) - float(nielsen_totals.loc[brand])
                    diffs.append((brand, abs(diff), diff))
                diffs.sort(key=lambda x: x[1], reverse=True)
                best_brand, _, signed = diffs[0]
                q.append(
                    {
                        "question": "Compare Nielsen brand sales vs Sales net sales — which brand has the biggest difference?",
                        "expected_answer": f"{best_brand} ({signed:.2f})",
                    }
                )

    # 20) Correlation direction (discount vs quantity) if both exist
    if "discount" in metrics and "quantity" in metrics:
        disc = pd.to_numeric(sales_df[metrics["discount"]], errors="coerce")
        qty = pd.to_numeric(sales_df[metrics["quantity"]], errors="coerce")
        corr = disc.corr(qty)
        if pd.notna(corr):
            direction = "positive" if corr > 0.05 else "negative" if corr < -0.05 else "weak/none"
            q.append(
                {
                    "question": "Does higher discount correlate with higher sales quantity?",
                    "expected_answer": direction,
                }
            )

    # Ensure exactly 20 by trimming or padding with safe structural questions
    while len(q) < 20:
        q.append(
            {
                "question": "What is the name of the Sales sheet in this workbook? (return the sheet name)",
                "expected_answer": sales_name,
            }
        )
    q = q[:20]

    return q


def write_question_bank(workbook_path: str, out_path: Path) -> None:
    bank = build_question_bank(workbook_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bank, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Benchmark: call LangGraph agent & compare answers
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    return "".join(ch.lower() for ch in (s or "") if ch.isalnum() or ch.isspace()).strip()


def _extract_numbers(text: str) -> List[float]:
    if not text:
        return []
    nums = re.findall(r"-?\d+(?:,\d{3})*(?:\.\d+)?", text)
    out: List[float] = []
    for n in nums:
        try:
            out.append(float(n.replace(",", "")))
        except Exception:
            continue
    return out


def _is_correct(agent_answer: str, expected: str) -> bool:
    """
    Lightweight comparison:
    - If expected contains a number, compare against numbers in agent answer.
    - Otherwise: token/substring match after normalization.
    """
    a = (agent_answer or "").strip()
    e = (expected or "").strip()

    expected_nums = _extract_numbers(e)
    if expected_nums:
        target = expected_nums[0]
        agent_nums = _extract_numbers(a)
        if not agent_nums:
            return False
        for cand in agent_nums:
            if target == 0:
                if abs(cand - target) < 1e-6:
                    return True
            else:
                if abs(cand - target) / (abs(target) + 1e-9) < 0.05:
                    return True
        return False

    na = _normalize(a)
    ne = _normalize(e)
    if not ne:
        return False
    if ne in na or na in ne:
        return True

    expected_tokens = [t for t in ne.split() if len(t) >= 3]
    if not expected_tokens:
        return False
    hits = sum(1 for t in expected_tokens if t in na)
    return hits / len(expected_tokens) >= 0.6


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def run_for_workbook(
    *,
    workbook_path: str,
    question_bank_path: Path,
    results_csv_path: Path,
) -> None:
    # 1) Build/update question bank
    write_question_bank(workbook_path, question_bank_path)
    bank: List[Dict[str, Any]] = _load_json(question_bank_path)

    # 2) Build Q&A LangGraph
    qa_graph = build_qa_graph()

    # 3) Run each question through the agent
    results: List[Dict[str, Any]] = []

    for item in bank:
        question = str(item.get("question", "")).strip()
        expected = str(item.get("expected_answer", "")).strip()

        start = time.perf_counter()
        state = qa_graph.invoke({"question": question, "workbook_path": workbook_path})
        elapsed = time.perf_counter() - start

        agent_answer = str(state.get("answer", "")).strip()
        correct = _is_correct(agent_answer, expected)

        results.append(
            {
                "dataset": Path(workbook_path).name,
                "question": question,
                "expected_answer": expected,
                "agent_answer": agent_answer,
                "response_time_seconds": f"{elapsed:.4f}",
                "correct_or_not": str(bool(correct)),
                "status": str(state.get("status", "")),
            }
        )

    # 4) Write CSV (overwrite each run)
    results_csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "dataset",
        "question",
        "expected_answer",
        "agent_answer",
        "response_time_seconds",
        "correct_or_not",
        "status",
    ]
    with results_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


# ---------------------------------------------------------------------------
# Report generation (markdown)
# ---------------------------------------------------------------------------

def _read_csv(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def generate_report(
    *,
    question_bank_path: Path,
    results_csv_path: Path,
    output_md_path: Path,
) -> None:
    rows = _read_csv(results_csv_path)
    bank = _load_json(question_bank_path)

    total_questions = len(rows)
    correct_answers = sum(1 for r in rows if str(r.get("correct_or_not", "")).lower() == "true")
    accuracy_percentage = (correct_answers / total_questions * 100.0) if total_questions else 0.0

    times: List[float] = []
    for r in rows:
        try:
            times.append(float(r.get("response_time_seconds", "0") or 0))
        except Exception:
            continue
    average_response_time = sum(times) / len(times) if times else 0.0

    output_md_path.parent.mkdir(parents=True, exist_ok=True)

    png_ref = "evaluation/langgraph_pipeline.png"

    md: List[str] = []
    md.append("## Section 1 — System Overview\n")
    md.append(
        "- The system uses **FastAPI** for HTTP endpoints and **LangGraph** to orchestrate a multi-step Q&A workflow.\n"
        "- The benchmark calls the existing compiled LangGraph Q&A workflow directly (Python import), without changing the API.\n"
    )

    md.append("\n## Section 2 — Pipeline Visualization\n")
    md.append(f"- Pipeline PNG: `{png_ref}`\n")

    md.append("\n## Section 3 — Benchmark Setup\n")
    md.append(f"- Dataset used: workbook used by the benchmark run\n")
    md.append(f"- Number of questions: **{len(bank)}**\n")

    md.append("\n## Section 4 — Results Table\n")
    md.append("| Question | Expected Answer | Agent Answer | Response Time (s) | Correct |\n")
    md.append("|---|---|---|---:|:---:|\n")
    for r in rows:
        q = str(r.get("question", "")).replace("\n", " ")
        exp = str(r.get("expected_answer", "")).replace("\n", " ")
        ans = str(r.get("agent_answer", "")).replace("\n", " ")
        t = str(r.get("response_time_seconds", ""))
        c = "✅" if str(r.get("correct_or_not", "")).lower() == "true" else "❌"
        md.append(f"| {q} | {exp} | {ans} | {t} | {c} |\n")

    md.append("\n## Section 5 — Summary Metrics\n")
    md.append(f"- Total questions: **{total_questions}**\n")
    md.append(f"- Correct answers: **{correct_answers}**\n")
    md.append(f"- Accuracy percentage: **{accuracy_percentage:.2f}%**\n")
    md.append(f"- Average response time: **{average_response_time:.3f}s**\n")

    md.append("\n## Section 6 — Observed Bottlenecks\n")
    md.append(
        "- If response times increase with larger datasets, likely bottlenecks are:\n"
        "  - Workbook parsing time (pandas reading multiple sheets)\n"
        "  - LLM latency (network + model compute)\n"
        "  - Larger prompts due to higher cardinality columns\n"
    )

    output_md_path.write_text("".join(md), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export LangGraph pipeline PNG, run benchmark, and generate a performance report."
    )
    parser.add_argument(
        "--workbook",
        default="outputs/consolidated_output.xlsx",
        help="Workbook path to benchmark (default: outputs/consolidated_output.xlsx).",
    )
    parser.add_argument(
        "--datasets-dir",
        default=None,
        help="Optional directory containing multiple datasets (*.xlsx) to benchmark.",
    )
    parser.add_argument(
        "--question-bank",
        default="evaluation/question_bank.json",
        help="Question bank path (will be regenerated with expected answers).",
    )
    parser.add_argument(
        "--results",
        default="evaluation/benchmark_results.csv",
        help="Output CSV results path.",
    )
    parser.add_argument(
        "--report",
        default="evaluation/performance_report.md",
        help="Output markdown report path.",
    )
    parser.add_argument(
        "--graph-only",
        action="store_true",
        help="Only export the LangGraph PNG and exit.",
    )

    args = parser.parse_args()

    results_path = Path(args.results)
    question_bank_path = Path(args.question_bank)
    report_path = Path(args.report)
    png_path = Path("evaluation/langgraph_pipeline.png")

    # Always (re)export pipeline PNG
    export_pipeline_png(png_path)

    if args.graph_only:
        print(f"Wrote pipeline PNG to: {png_path}")
        return

    # Single-workbook mode
    if not args.datasets_dir:
        run_for_workbook(
            workbook_path=args.workbook,
            question_bank_path=question_bank_path,
            results_csv_path=results_path,
        )
    else:
        # Multi-dataset mode: aggregate rows across all workbooks into one CSV.
        datasets_dir = Path(args.datasets_dir)
        workbooks = sorted([p for p in datasets_dir.glob("*.xlsx")])
        if not workbooks:
            raise SystemExit(f"No .xlsx files found in: {datasets_dir}")

        all_rows: List[Dict[str, Any]] = []
        tmp_results = results_path.parent / "_tmp_results.csv"

        for wb in workbooks:
            run_for_workbook(
                workbook_path=str(wb),
                question_bank_path=question_bank_path,
                results_csv_path=tmp_results,
            )
            with tmp_results.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                all_rows.extend(list(reader))

        results_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(all_rows[0].keys()) if all_rows else []
        with results_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)

    # Generate report every run (overwrite)
    generate_report(
        question_bank_path=question_bank_path,
        results_csv_path=results_path,
        output_md_path=report_path,
    )

    print(f"Wrote pipeline PNG to: {png_path}")
    print(f"Wrote results CSV to: {results_path}")
    print(f"Wrote report to: {report_path}")


if __name__ == "__main__":
    main()

