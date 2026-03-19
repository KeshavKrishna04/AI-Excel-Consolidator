from __future__ import annotations

"""
ADVANCED BENCHMARK EVALUATION SCRIPT

This script evaluates the QA LangGraph agent using multiple layers of metrics.

Metrics implemented:

CORE CORRECTNESS
- exact_match
- numeric_match
- zero_semantic_match
- list_match
- semantic_similarity
- token_overlap

QUALITY METRICS
- reasoning_score
- hallucination_score

This evaluation design mimics multi-layer evaluation used in
OpenAI / Anthropic / LangChain style agent benchmarks.
"""

import argparse
import base64
import json
import random
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from sentence_transformers import SentenceTransformer, util

# Matplotlib is used only for epoch stability plots.
# Keep it optional so benchmarks still run without it.
_HAS_MATPLOTLIB = False
try:
    import matplotlib  # type: ignore

    matplotlib.use("Agg")  # non-interactive backend for headless runs
    import matplotlib.pyplot as plt  # type: ignore

    _HAS_MATPLOTLIB = True
except Exception:
    _HAS_MATPLOTLIB = False

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from graph.qa_graph import build_qa_graph


# -----------------------------------------------------------
# GRAPH EXPORT
# -----------------------------------------------------------

def _render_mermaid_png_via_mermaid_ink(mermaid: str) -> bytes:
    b64 = base64.urlsafe_b64encode(mermaid.encode("utf-8")).decode("ascii").rstrip("=")
    url = f"https://mermaid.ink/img/{b64}"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content


def export_pipeline_png(png_path: Path):

    png_path.parent.mkdir(parents=True, exist_ok=True)

    graph = build_qa_graph()
    drawable = graph.get_graph()

    mermaid = drawable.draw_mermaid()

    try:
        png = drawable.draw_png()
    except Exception:
        try:
            png = _render_mermaid_png_via_mermaid_ink(mermaid)
        except Exception as exc:
            # Best-effort only: graph visualization must not block benchmarks.
            print(
                f"Warning: failed to export pipeline PNG to {png_path}. "
                f"Install pygraphviz for local rendering, or check network access. "
                f"Details: {exc}"
            )
            return

    try:
        png_path.write_bytes(png)
    except Exception as exc:
        print(f"Warning: failed to write pipeline PNG to {png_path}: {exc}")
        return


# -----------------------------------------------------------
# SEMANTIC MODEL
# -----------------------------------------------------------

_SEMANTIC_MODEL: Optional[SentenceTransformer] = None


def _get_semantic_model():

    global _SEMANTIC_MODEL

    if _SEMANTIC_MODEL is None:

        _SEMANTIC_MODEL = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2"
        )

    return _SEMANTIC_MODEL


def semantic_similarity(a: str, b: str):

    if not a or not b:
        return 0.0

    model = _get_semantic_model()

    emb = model.encode([a, b], convert_to_tensor=True)

    return util.cos_sim(emb[0], emb[1]).item()


# -----------------------------------------------------------
# TEXT UTILITIES
# -----------------------------------------------------------

def normalize_text(text: str):

    text = (text or "").lower()

    text = text.replace(",", "")

    text = re.sub(r"[^a-z0-9\s]", " ", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def extract_numbers(text: str):

    nums = re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))

    out = []

    for n in nums:
        try:
            out.append(float(n))
        except:
            pass

    return out


# -----------------------------------------------------------
# ZERO SEMANTIC MATCH
# -----------------------------------------------------------

def zero_semantic_match(expected: str, agent: str):

    exp_nums = extract_numbers(expected)

    if not exp_nums or exp_nums[0] != 0:
        return False

    text = normalize_text(agent)

    phrases = [
        "does not appear",
        "not present",
        "no occurrence",
        "none",
        "not found",
        "zero",
        "no records",
        "no rows",
    ]

    return any(p in text for p in phrases)


# -----------------------------------------------------------
# LIST MATCH
# -----------------------------------------------------------

def compare_lists(expected: str, agent: str):

    if "," not in expected:
        return False

    exp = {normalize_text(x) for x in expected.split(",")}
    ans = {normalize_text(x) for x in agent.split(",")}

    overlap = len(exp.intersection(ans))

    return overlap / len(exp) >= 0.6


# -----------------------------------------------------------
# TOKEN OVERLAP
# -----------------------------------------------------------

def token_overlap(a: str, b: str):

    ta = set(normalize_text(a).split())
    tb = set(normalize_text(b).split())

    if not ta or not tb:
        return 0.0

    return len(ta.intersection(tb)) / min(len(ta), len(tb))


# -----------------------------------------------------------
# REASONING SCORE
# -----------------------------------------------------------

def reasoning_score(answer: str):

    indicators = [
        "because",
        "therefore",
        "since",
        "as a result",
        "this means",
        "so",
        "hence",
    ]

    text = normalize_text(answer)

    score = 0

    for w in indicators:
        if w in text:
            score += 1

    return min(score / len(indicators), 1.0)


# -----------------------------------------------------------
# HALLUCINATION SCORE
# -----------------------------------------------------------

def hallucination_score(answer: str, question: str, expected: str):

    a = set(normalize_text(answer).split())
    q = set(normalize_text(question).split())
    e = set(normalize_text(expected).split())

    reference = q.union(e)

    extra = a - reference

    if not a:
        return 0.0

    return len(extra) / len(a)


# -----------------------------------------------------------
# METRIC ENGINE
# -----------------------------------------------------------

def compute_metrics(agent_answer: str, expected: str, question: str):

    a = agent_answer.strip()
    e = expected.strip()

    na = normalize_text(a)
    ne = normalize_text(e)

    exact_match = na == ne and bool(ne)

    numeric_match = False

    exp_nums = extract_numbers(e)
    ans_nums = extract_numbers(a)

    if exp_nums and ans_nums:

        for t in exp_nums:
            for c in ans_nums:

                if t == 0:
                    if abs(c) < 1e-6:
                        numeric_match = True
                        break
                else:
                    if abs(c - t) / abs(t) < 0.03:
                        numeric_match = True
                        break

    zero_match = zero_semantic_match(e, a)

    list_match = compare_lists(e, a)

    sem = semantic_similarity(a, e)

    token = token_overlap(a, e)

    semantic_match = sem >= 0.65

    reason = reasoning_score(a)

    halluc = hallucination_score(a, question, e)

    overall = any(
        [
            exact_match,
            numeric_match,
            zero_match,
            list_match,
            semantic_match,
            token >= 0.5,
        ]
    )

    return dict(
        exact_match=exact_match,
        numeric_match=numeric_match,
        zero_match=zero_match,
        list_match=list_match,
        semantic_similarity=sem,
        token_overlap=token,
        reasoning_score=reason,
        hallucination_score=halluc,
        overall_correct=overall,
    )


# -----------------------------------------------------------
# BENCHMARK EXECUTION
# -----------------------------------------------------------

def _extract_token_usage(state: Any) -> Dict[str, Optional[int]]:

    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    if isinstance(state, dict):

        usage_dict: Optional[Dict[str, Any]] = None

        for key in ("usage", "llm_usage", "token_usage"):
            if key in state and isinstance(state[key], dict):
                usage_dict = state[key]
                break

        if usage_dict:

            def _first_int(d: Dict[str, Any], keys: List[str]) -> Optional[int]:
                for k in keys:
                    if k in d and isinstance(d[k], (int, float)):
                        return int(d[k])
                return None

            prompt_tokens = _first_int(
                usage_dict, ["prompt_tokens", "prompt", "input_tokens"]
            )
            completion_tokens = _first_int(
                usage_dict, ["completion_tokens", "completion", "output_tokens"]
            )
            total_tokens = _first_int(
                usage_dict,
                ["total_tokens", "total", "tokens"],
            )

    return dict(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def run_for_workbook(
    *,
    workbook_path: str,
    question_bank_path: Path,
    results_csv_path: Path,
    epoch_index: int,
    epoch_start_timestamp: str,
):

    original_bank: List[Dict[str, Any]] = json.loads(
        question_bank_path.read_text(encoding="utf-8")
    )

    # Create a fresh randomized question order for this epoch
    questions_for_epoch = list(original_bank)
    random.shuffle(questions_for_epoch)

    print(f"\nEpoch {epoch_index} Question Order:")
    for i, item in enumerate(questions_for_epoch, start=1):
        print(f"{i}. {item.get('question', '')}")

    graph = build_qa_graph()

    results = []

    for idx, item in enumerate(questions_for_epoch, start=1):

        question = item["question"]
        expected = item["expected_answer"]

        question_start_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        start = time.perf_counter()

        state: Any = None
        error_message: Optional[str] = None

        try:
            state = graph.invoke(
                {
                    "question": question,
                    "workbook_path": workbook_path,
                }
            )
        except Exception as exc:
            error_message = str(exc)
        finally:
            elapsed = time.perf_counter() - start

        if isinstance(state, dict):
            agent = str(state.get("answer", "")).strip()
            context_used = str(state.get("context_used", "") or "").strip()
            token_usage = _extract_token_usage(state)
        else:
            agent = ""
            context_used = ""
            token_usage = dict(
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
            )

        print(
            f"Q{idx} latency: {elapsed:.2f}s tokens: "
            f"{token_usage['total_tokens'] if token_usage['total_tokens'] is not None else 'N/A'}"
        )

        metrics = compute_metrics(agent, expected, question)

        results.append(
            dict(
                dataset=Path(workbook_path).name,
                epoch=epoch_index,
                epoch_start_time=epoch_start_timestamp,
                question_index=idx,
                question_start_time=question_start_ts,
                question=question,
                expected_answer=expected,
                agent_answer=agent,
                context_used=context_used,
                response_time_seconds=f"{elapsed:.4f}",
                latency_seconds=elapsed,
                prompt_tokens=token_usage["prompt_tokens"],
                completion_tokens=token_usage["completion_tokens"],
                total_tokens=token_usage["total_tokens"],
                error=error_message,
                **metrics,
            )
        )

    df = pd.DataFrame(results)

    results_csv_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(results_csv_path, index=False)


# -----------------------------------------------------------
# EPOCH STABILITY PLOTS
# -----------------------------------------------------------

def generate_epoch_plots(*, epoch_df: pd.DataFrame, evaluation_dir: Path) -> Dict[str, Path]:
    """
    Generate epoch-wise stability plots from epoch_results.csv-like DataFrame.
    Returns a dict of plot keys to file paths.
    """

    if not _HAS_MATPLOTLIB:
        raise RuntimeError(
            "matplotlib is not installed. Install it with: pip install matplotlib"
        )

    evaluation_dir.mkdir(parents=True, exist_ok=True)

    epochs = epoch_df["epoch"].astype(int).tolist()
    accuracies = epoch_df["accuracy"].astype(float).tolist()
    reasoning_scores = epoch_df["reasoning_score"].astype(float).tolist()
    hallucination_scores = epoch_df["hallucination_score"].astype(float).tolist()
    latencies = epoch_df["avg_latency"].astype(float).tolist()

    def _save_plot(*, y: List[float], title: str, xlabel: str, ylabel: str, out_path: Path):
        plt.figure(figsize=(7, 4))
        plt.plot(epochs, y, marker="o")
        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(out_path, dpi=160)
        plt.close()

    paths: Dict[str, Path] = {
        "accuracy": evaluation_dir / "epoch_accuracy.png",
        "latency": evaluation_dir / "epoch_latency.png",
        "hallucination": evaluation_dir / "epoch_hallucination.png",
        "reasoning": evaluation_dir / "epoch_reasoning.png",
    }

    _save_plot(
        y=accuracies,
        title="Accuracy vs Epoch",
        xlabel="Epoch",
        ylabel="Accuracy",
        out_path=paths["accuracy"],
    )
    _save_plot(
        y=latencies,
        title="Average Latency vs Epoch",
        xlabel="Epoch",
        ylabel="Average Latency (s)",
        out_path=paths["latency"],
    )
    _save_plot(
        y=hallucination_scores,
        title="Hallucination Score vs Epoch",
        xlabel="Epoch",
        ylabel="Hallucination Score",
        out_path=paths["hallucination"],
    )
    _save_plot(
        y=reasoning_scores,
        title="Reasoning Score vs Epoch",
        xlabel="Epoch",
        ylabel="Reasoning Score",
        out_path=paths["reasoning"],
    )

    return paths


# -----------------------------------------------------------
# REPORT GENERATION
# -----------------------------------------------------------

def generate_report(
    *,
    results_csv_path: Path,
    output_md_path: Path,
    epoch_results_csv_path: Optional[Path] = None,
    benchmark_runtime_seconds: Optional[float] = None,
):

    df = pd.read_csv(results_csv_path)

    total = len(df)

    accuracy = df["overall_correct"].mean() * 100

    reasoning_avg = df["reasoning_score"].mean()

    halluc_avg = df["hallucination_score"].mean()

    md: List[str] = []

    md.append("# Benchmark Report\n")

    md.append("## Summary\n")

    md.append(f"- Total Questions: **{total}**\n")
    md.append(f"- Accuracy: **{accuracy:.2f}%**\n")
    md.append(f"- Avg Reasoning Score: **{reasoning_avg:.2f}**\n")
    md.append(f"- Avg Hallucination Score: **{halluc_avg:.2f}**\n")

    md.append("\n## Detailed Results\n")

    md.append(
        "|Question|Expected|Agent|Correct|Reasoning|Hallucination|Latency (seconds)|Tokens|\n"
    )
    md.append("|---|---|---|---|---|---|---|---|\n")

    for _, r in df.iterrows():

        latency_val = None
        if "latency_seconds" in r and not pd.isna(r["latency_seconds"]):
            latency_val = float(r["latency_seconds"])
        elif "response_time_seconds" in r and not pd.isna(
            r["response_time_seconds"]
        ):
            latency_val = float(r["response_time_seconds"])

        tokens_val = r["total_tokens"] if "total_tokens" in r else None

        if latency_val is not None:
            latency_str = f"{latency_val:.4f}"
        else:
            latency_str = "N/A"

        tokens_str = (
            f"{int(tokens_val)}" if tokens_val is not None and pd.notna(tokens_val) else "N/A"
        )

        md.append(
            f"|{r['question']}|{r['expected_answer']}|{r['agent_answer']}|"
            f"{'YES' if r['overall_correct'] else 'NO'}|"
            f"{r['reasoning_score']:.2f}|{r['hallucination_score']:.2f}|"
            f"{latency_str}|{tokens_str}|\n"
        )

    # -------------------------------------------------------
    # Top 3 vs Bottom 3 by latency
    # -------------------------------------------------------
    md.append("\n## Analysis: Top 3 vs Bottom 3 by Latency\n\n")
    latency_col = "latency_seconds" if "latency_seconds" in df.columns else "response_time_seconds"
    if latency_col in df.columns:
        df_sorted = df.copy()
        df_sorted["_lat"] = pd.to_numeric(df_sorted[latency_col], errors="coerce")
        df_sorted = df_sorted.dropna(subset=["_lat"]).sort_values("_lat", ascending=False)
        n = len(df_sorted)
        top3 = df_sorted.head(min(3, n))
        bot3 = df_sorted.tail(min(3, n)).iloc[::-1]

        md.append("### Top 3 Slowest (Highest Latency)\n\n")
        md.append("|#|Question|Latency (s)|Tokens|Reasoning|Hallucination|Correct|\n")
        md.append("|---|---|---|---|---|---|---|\n")
        def _trunc(s: str, max_len: int = 55) -> str:
            s = str(s)
            return (s[:max_len] + "...") if len(s) > max_len else s

        for i, (_, r) in enumerate(top3.iterrows(), 1):
            lat = float(r["_lat"])
            tok = r.get("total_tokens")
            tok_str = f"{int(tok)}" if pd.notna(tok) else "N/A"
            md.append(
                f"|{i}|{_trunc(r['question'])}|{lat:.2f}|{tok_str}|"
                f"{r['reasoning_score']:.2f}|{r['hallucination_score']:.2f}|"
                f"{'YES' if r['overall_correct'] else 'NO'}|\n"
            )

        md.append("\n### Bottom 3 Fastest (Lowest Latency)\n\n")
        md.append("|#|Question|Latency (s)|Tokens|Reasoning|Hallucination|Correct|\n")
        md.append("|---|---|---|---|---|---|---|\n")
        for i, (_, r) in enumerate(bot3.iterrows(), 1):
            lat = float(r["_lat"])
            tok = r.get("total_tokens")
            tok_str = f"{int(tok)}" if pd.notna(tok) else "N/A"
            md.append(
                f"|{i}|{_trunc(r['question'])}|{lat:.2f}|{tok_str}|"
                f"{r['reasoning_score']:.2f}|{r['hallucination_score']:.2f}|"
                f"{'YES' if r['overall_correct'] else 'NO'}|\n"
            )

        t3_lat = top3["_lat"].mean()
        b3_lat = bot3["_lat"].mean()
        t3_tok = top3["total_tokens"].dropna()
        b3_tok = bot3["total_tokens"].dropna()
        md.append("\n**Summary:** Top 3 avg latency: **{:.2f}s** | Bottom 3 avg latency: **{:.2f}s**\n".format(t3_lat, b3_lat))
        if not t3_tok.empty and not b3_tok.empty:
            md.append("Top 3 avg tokens: **{:.0f}** | Bottom 3 avg tokens: **{:.0f}**\n".format(t3_tok.mean(), b3_tok.mean()))
    else:
        md.append("Latency data not available for analysis.\n")

    # -------------------------------------------------------
    # Agent context used (per question)
    # -------------------------------------------------------
    if "context_used" in df.columns:
        ctx_series = df["context_used"].fillna("")
        if ctx_series.str.strip().any():
            md.append("\n## Agent Context Used (Per Question)\n\n")
            md.append("For each question, the agent reports which sources and logic it used to derive the answer.\n\n")
            for _, r in df.iterrows():
                q = r.get("question", "")
                ctx = str(r.get("context_used", "") or "").strip()
                if not ctx:
                    ctx = "_No context reported._"
                md.append(f"### {q}\n\n{ctx}\n\n")

    # -------------------------------------------------------
    # Multi-epoch benchmark results (if available)
    # -------------------------------------------------------
    if epoch_results_csv_path is not None and epoch_results_csv_path.exists():

        epoch_df = pd.read_csv(epoch_results_csv_path)

        if not epoch_df.empty:

            md.append("\n## Multi-Epoch Benchmark Results\n")

            md.append("\n### Epoch Results Table\n\n")
            md.append(
                "|Epoch|Accuracy|Reasoning|Hallucination|Avg Latency (s)|Avg Tokens|\n"
            )
            md.append("|---|---|---|---|---|---|\n")

            for _, r in epoch_df.iterrows():
                avg_tokens_val = r["avg_tokens"] if "avg_tokens" in r else float("nan")
                if not pd.isna(avg_tokens_val):
                    avg_tokens_str = f"{avg_tokens_val:.2f}"
                else:
                    avg_tokens_str = "N/A"

                md.append(
                    f"|{int(r['epoch'])}|{r['accuracy']:.4f}|{r['reasoning_score']:.4f}|"
                    f"{r['hallucination_score']:.4f}|{r['avg_latency']:.4f}|"
                    f"{avg_tokens_str}|\n"
                )

            acc_values = epoch_df["accuracy"].tolist()

            mean_accuracy = statistics.mean(acc_values)
            std_accuracy = statistics.pstdev(acc_values) if len(acc_values) > 1 else 0.0
            min_accuracy = min(acc_values)
            max_accuracy = max(acc_values)

            md.append("\n### Benchmark Stability Summary\n\n")
            md.append(f"- Mean Accuracy: **{mean_accuracy:.4f}**\n")
            md.append(f"- Std Deviation: **{std_accuracy:.4f}**\n")
            md.append(f"- Min Accuracy: **{min_accuracy:.4f}**\n")
            md.append(f"- Max Accuracy: **{max_accuracy:.4f}**\n")

            # -------------------------------------------------------
            # Epoch stability plots (if present)
            # -------------------------------------------------------
            eval_dir = output_md_path.parent
            plot_files = [
                ("Accuracy vs Epoch", eval_dir / "epoch_accuracy.png"),
                ("Latency vs Epoch", eval_dir / "epoch_latency.png"),
                ("Hallucination vs Epoch", eval_dir / "epoch_hallucination.png"),
                ("Reasoning vs Epoch", eval_dir / "epoch_reasoning.png"),
            ]
            if all(p.exists() for _, p in plot_files):
                md.append("\n## Epoch Stability Plots\n\n")
                md.append("![Accuracy vs Epoch](epoch_accuracy.png)\n")
                md.append("![Latency vs Epoch](epoch_latency.png)\n")
                md.append("![Hallucination vs Epoch](epoch_hallucination.png)\n")
                md.append("![Reasoning vs Epoch](epoch_reasoning.png)\n")

    # -------------------------------------------------------
    # Execution statistics
    # -------------------------------------------------------
    md.append("\n## Execution Statistics\n\n")

    total_tokens_used: Optional[float] = None
    avg_tokens_per_query: Optional[float] = None
    avg_query_latency: Optional[float] = None

    if "total_tokens" in df.columns:
        token_series = df["total_tokens"].dropna()
        if not token_series.empty:
            total_tokens_used = float(token_series.sum())
            avg_tokens_per_query = float(token_series.mean())

    if "latency_seconds" in df.columns:
        latency_series = df["latency_seconds"].dropna().astype(float)
    elif "response_time_seconds" in df.columns:
        latency_series = df["response_time_seconds"].dropna().astype(float)
    else:
        latency_series = pd.Series(dtype=float)

    if not latency_series.empty:
        avg_query_latency = float(latency_series.mean())

    md.append(
        f"- Total Tokens Used: **{int(total_tokens_used)}**\n"
        if total_tokens_used is not None
        else "- Total Tokens Used: **N/A**\n"
    )
    md.append(
        f"- Average Tokens per Query: **{avg_tokens_per_query:.2f}**\n"
        if avg_tokens_per_query is not None
        else "- Average Tokens per Query: **N/A**\n"
    )
    md.append(
        f"- Average Query Latency: **{avg_query_latency:.4f} seconds**\n"
        if avg_query_latency is not None
        else "- Average Query Latency: **N/A**\n"
    )

    if benchmark_runtime_seconds is not None:
        md.append(
            f"- Total Benchmark Runtime: **{benchmark_runtime_seconds:.2f} seconds**\n"
        )
    else:
        md.append("- Total Benchmark Runtime: **N/A**\n")

    output_md_path.write_text("".join(md), encoding="utf-8")


# -----------------------------------------------------------
# CLI
# -----------------------------------------------------------

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument("--workbook", default="outputs/consolidated_output.xlsx")

    parser.add_argument("--results", default="evaluation/benchmark_results.csv")

    parser.add_argument("--report", default="evaluation/performance_report.md")

    parser.add_argument(
        "--epochs",
        type=int,
        default=5,
        help="Number of epochs to run the full benchmark.",
    )

    args = parser.parse_args()

    results_path = Path(args.results)

    export_pipeline_png(Path("evaluation/langgraph_pipeline.png"))

    num_epochs = args.epochs if args.epochs and args.epochs > 0 else 1

    print(f"Starting Multi-Epoch Benchmark ({num_epochs} epochs)")

    benchmark_start = time.perf_counter()

    epoch_results: List[Dict[str, Any]] = []

    epoch_csv_path = Path("evaluation/epoch_results.csv")

    for epoch in range(1, num_epochs + 1):

        epoch_start_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\nEpoch {epoch}/{num_epochs} running...")
        print(f"Epoch {epoch} started: {epoch_start_ts}")

        run_for_workbook(
            workbook_path=args.workbook,
            question_bank_path=Path("evaluation/question_bank.json"),
            results_csv_path=results_path,
            epoch_index=epoch,
            epoch_start_timestamp=epoch_start_ts,
        )

        df = pd.read_csv(results_path)

        accuracy = df["overall_correct"].mean()
        reasoning_avg = df["reasoning_score"].mean()
        halluc_avg = df["hallucination_score"].mean()

        try:
            avg_latency = df["latency_seconds"].astype(float).mean()
        except Exception:
            try:
                avg_latency = df["response_time_seconds"].astype(float).mean()
            except Exception:
                avg_latency = float("nan")

        if "total_tokens" in df.columns:
            token_series = df["total_tokens"].dropna()
            avg_tokens = (
                float(token_series.mean()) if not token_series.empty else float("nan")
            )
        else:
            avg_tokens = float("nan")

        epoch_end_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        epoch_results.append(
            {
                "epoch": epoch,
                "epoch_start": epoch_start_ts,
                "epoch_end": epoch_end_ts,
                "timestamp": epoch_end_ts,
                "accuracy": float(accuracy),
                "reasoning_score": float(reasoning_avg),
                "hallucination_score": float(halluc_avg),
                "avg_latency": float(avg_latency),
                "avg_tokens": float(avg_tokens),
            }
        )

        print(f"Epoch {epoch} Accuracy: {accuracy:.4f}")

    if epoch_results:

        epoch_df = pd.DataFrame(epoch_results)
        epoch_csv_path.parent.mkdir(parents=True, exist_ok=True)
        epoch_df.to_csv(epoch_csv_path, index=False)

        # Generate epoch stability plots automatically.
        try:
            generate_epoch_plots(epoch_df=epoch_df, evaluation_dir=Path("evaluation"))
        except Exception as exc:
            print(f"Warning: failed to generate epoch plots: {exc}")

        acc_values = [row["accuracy"] for row in epoch_results]

        mean_accuracy = statistics.mean(acc_values)
        std_accuracy = (
            statistics.pstdev(acc_values) if len(acc_values) > 1 else 0.0
        )
        min_accuracy = min(acc_values)
        max_accuracy = max(acc_values)

        print("\nBenchmark Summary")
        print(f"Mean Accuracy: {mean_accuracy:.4f}")
        print(f"Std Dev: {std_accuracy:.4f}")
        print(f"Min Accuracy: {min_accuracy:.4f}")
        print(f"Max Accuracy: {max_accuracy:.4f}")

    benchmark_runtime = time.perf_counter() - benchmark_start

    generate_report(
        results_csv_path=results_path,
        output_md_path=Path(args.report),
        epoch_results_csv_path=epoch_csv_path,
        benchmark_runtime_seconds=benchmark_runtime,
    )


if __name__ == "__main__":
    main()