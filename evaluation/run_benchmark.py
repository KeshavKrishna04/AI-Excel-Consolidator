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
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from sentence_transformers import SentenceTransformer, util

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
        png = _render_mermaid_png_via_mermaid_ink(mermaid)

    png_path.write_bytes(png)


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

def run_for_workbook(*, workbook_path: str, question_bank_path: Path, results_csv_path: Path):

    bank = json.loads(question_bank_path.read_text())

    graph = build_qa_graph()

    results = []

    for item in bank:

        question = item["question"]
        expected = item["expected_answer"]

        start = time.perf_counter()

        state = graph.invoke(
            {
                "question": question,
                "workbook_path": workbook_path,
            }
        )

        elapsed = time.perf_counter() - start

        agent = str(state.get("answer", "")).strip()

        metrics = compute_metrics(agent, expected, question)

        results.append(
            dict(
                dataset=Path(workbook_path).name,
                question=question,
                expected_answer=expected,
                agent_answer=agent,
                response_time_seconds=f"{elapsed:.4f}",
                **metrics,
            )
        )

    df = pd.DataFrame(results)

    results_csv_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(results_csv_path, index=False)


# -----------------------------------------------------------
# REPORT GENERATION
# -----------------------------------------------------------

def generate_report(*, results_csv_path: Path, output_md_path: Path):

    df = pd.read_csv(results_csv_path)

    total = len(df)

    accuracy = df["overall_correct"].mean() * 100

    reasoning_avg = df["reasoning_score"].mean()

    halluc_avg = df["hallucination_score"].mean()

    md = []

    md.append("# Benchmark Report\n")

    md.append("## Summary\n")

    md.append(f"- Total Questions: **{total}**\n")
    md.append(f"- Accuracy: **{accuracy:.2f}%**\n")
    md.append(f"- Avg Reasoning Score: **{reasoning_avg:.2f}**\n")
    md.append(f"- Avg Hallucination Score: **{halluc_avg:.2f}**\n")

    md.append("\n## Detailed Results\n")

    md.append("|Question|Expected|Agent|Correct|Reasoning|Hallucination|\n")
    md.append("|---|---|---|---|---|---|\n")

    for _, r in df.iterrows():

        md.append(
            f"|{r['question']}|{r['expected_answer']}|{r['agent_answer']}|{'YES' if r['overall_correct'] else 'NO'}|{r['reasoning_score']:.2f}|{r['hallucination_score']:.2f}|\n"
        )

    output_md_path.write_text("".join(md), encoding="utf-8")


# -----------------------------------------------------------
# CLI
# -----------------------------------------------------------

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument("--workbook", default="outputs/consolidated_output.xlsx")

    parser.add_argument("--results", default="evaluation/benchmark_results.csv")

    parser.add_argument("--report", default="evaluation/performance_report.md")

    args = parser.parse_args()

    results_path = Path(args.results)

    export_pipeline_png(Path("evaluation/langgraph_pipeline.png"))

    run_for_workbook(
        workbook_path=args.workbook,
        question_bank_path=Path("evaluation/question_bank.json"),
        results_csv_path=results_path,
    )

    generate_report(
        results_csv_path=results_path,
        output_md_path=Path(args.report),
    )


if __name__ == "__main__":
    main()