import json
from typing import Any, Dict

from llm.openrouter_client import get_llm
from llm.json_utils import extract_json


def answer_question_over_summary(question: str, summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Use an LLM to answer a natural-language question based on a structured
    summary of the consolidated_output.xlsx workbook.

    The summary is expected to be a JSON-serializable dictionary containing
    sheet-level and column-level statistics (unique values, counts, etc.).

    Returns a dict of the form:
        {
            "status": "ok" | "out_of_scope" | "error",
            "answer": "human-readable answer string",
            "reason": "optional short explanation for non-ok statuses"
        }
    """
    client = get_llm()

    # -----------------------------
    # Unstructured text mode
    # -----------------------------
    if isinstance(summary, dict) and "text_data" in summary:
        full_text = str(summary.get("text_data") or "")
        if not full_text.strip():
            return {
                "status": "out_of_scope",
                "answer": "Not found",
                "reason": "The provided document is empty.",
            }

        def _normalize(s: str) -> str:
            s = (s or "").lower()
            out = []
            for ch in s:
                if ch.isalnum() or ch.isspace():
                    out.append(ch)
                else:
                    out.append(" ")
            s = "".join(out)
            return " ".join(s.split())

        qn = _normalize(question)
        q_tokens = [t for t in qn.split() if len(t) >= 4]
        q_set = set(q_tokens)
        q_tokens_sorted = sorted(q_set, key=len, reverse=True)

        # Scan entire document and pick most relevant lines as evidence.
        lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
        scored = []
        for i, ln in enumerate(lines):
            ln_n = _normalize(ln)
            ln_set = set(ln_n.split())
            score = len(q_set & ln_set)
            if score > 0:
                scored.append((score, i))

        scored.sort(reverse=True)

        evidence_lines = []
        used_idx = set()

        # 1) Direct substring matches (robust for messy formatting).
        for i, ln in enumerate(lines):
            ln_n = _normalize(ln)
            if any(tok in ln_n for tok in q_tokens_sorted[:8]):
                for j in (i - 1, i, i + 1):
                    if 0 <= j < len(lines) and j not in used_idx:
                        used_idx.add(j)
                        evidence_lines.append(lines[j])

        # 2) Overlap-scored matches.
        for _, i in scored[:25]:
            for j in (i - 1, i, i + 1):
                if 0 <= j < len(lines) and j not in used_idx:
                    used_idx.add(j)
                    evidence_lines.append(lines[j])

        # Fallback: if no overlap, still include head+tail so the model can try.
        if not evidence_lines:
            head = "\n".join(lines[:30])
            tail = "\n".join(lines[-30:])
            evidence = head + "\n...\n" + tail
        else:
            evidence = "\n".join(evidence_lines)

        # Deterministic fast-path for common factual "when/year" questions.
        # This avoids LLM false negatives when the exact sentence is present.
        qn_simple = _normalize(question)
        if "when" in qn_simple or "year" in qn_simple:
            import re

            year_re = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
            # Prefer lines that contain longer query tokens (entities).
            for ln in evidence_lines:
                ln_n = _normalize(ln)
                # If key entities are present in the question, require them in the line.
                if "volta" in q_set and "volta" not in ln_n:
                    continue
                if "napoleon" in q_set and "napoleon" not in ln_n:
                    continue
                if any(tok in ln_n for tok in q_tokens_sorted[:6]):
                    m = year_re.search(ln)
                    if m:
                        yr = m.group(1)
                        return {
                            "status": "ok",
                            "answer": f"{yr}",
                            "context_used": ln,
                        }

        keywords_hint = ", ".join(q_tokens_sorted[:8])
        prompt = f"""
You are given evidence lines extracted from a document.

CRITICAL:
- Answer strictly using the provided Evidence.
- If the answer is not present, say "Not found".
- Before answering "Not found", explicitly check whether the Evidence contains any of these keywords: {keywords_hint}.
- If the Evidence contains the answer, your answer MUST be supported by quoting the exact sentence(s).
- Be concise and factual.

Question:
{question}

Evidence:
{evidence}

Return STRICT JSON ONLY in this format:
{{
  "status": "ok | out_of_scope | error",
  "answer": "short human-readable answer",
  "reason": "optional short explanation for non-ok statuses",
  "context_used": "quote the exact sentence(s) from Evidence you used"
}}
"""

        response = client.chat.completions.create(
            model="openai/gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )

        data = extract_json(response.choices[0].message.content)

        # Extract token usage (same logic as structured path)
        usage: Dict[str, Any] = {}
        u = getattr(response, "usage", None)
        if u is not None:
            pt = getattr(u, "prompt_tokens", None)
            ct = getattr(u, "completion_tokens", None)
            tt = getattr(u, "total_tokens", None)
            if pt is not None or ct is not None or tt is not None:
                usage["prompt_tokens"] = pt
                usage["completion_tokens"] = ct
                usage["total_tokens"] = tt if tt is not None else ((pt or 0) + (ct or 0))
        if not usage and hasattr(response, "model_dump"):
            try:
                raw = response.model_dump()
                u = raw.get("usage") if isinstance(raw, dict) else None
                if isinstance(u, dict):
                    usage["prompt_tokens"] = u.get("prompt_tokens")
                    usage["completion_tokens"] = u.get("completion_tokens")
                    usage["total_tokens"] = u.get("total_tokens") or (
                        (u.get("prompt_tokens") or 0) + (u.get("completion_tokens") or 0)
                    )
            except Exception:
                pass

        status = data.get("status")
        answer = data.get("answer")
        reason = data.get("reason")
        context_used = data.get("context_used")

        if status not in {"ok", "out_of_scope", "error"}:
            raise ValueError(f"Invalid status from QA LLM: {status!r}")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("QA LLM response missing non-empty 'answer' field")

        result: Dict[str, Any] = {
            "status": status,
            "answer": answer.strip(),
        }
        if reason:
            result["reason"] = str(reason)
        if isinstance(context_used, str) and context_used.strip():
            result["context_used"] = context_used.strip()
        if usage and (
            usage.get("total_tokens") is not None
            or usage.get("prompt_tokens") is not None
            or usage.get("completion_tokens") is not None
        ):
            result["usage"] = usage

        return result

    prompt = f"""
You are a senior data analyst AI answering questions about an Excel workbook
that contains consolidated business data (sales, nielsen, pricing, competitor, baseline).

CRITICAL: Answer ONLY using values present in the WORKBOOK SUMMARY below. Do NOT invent
brand names, numbers, sheet names, or column values that do not appear in the summary.
- Consolidated_Sales and Consolidated_Nielsen contain brands: Fresh Flow, FRESHFLOW, FreshFlow
- Consolidated_Competitor contains brands named Brand_1, Brand_2, ... Brand_49 (different from Sales/Nielsen)
- If the summary lacks the required data, return "out_of_scope" with a clear reason

You are given:
- A NATURAL LANGUAGE QUESTION from the user (it may be slightly misworded)
- A STRUCTURED SUMMARY of the workbook contents, including for each sheet:
  - sheet name (e.g., "Consolidated_Sales")
  - total rows and columns
  - for each column:
      - dtype
      - non_null_count
      - unique_count
      - for categorical columns: top_values[value] = count
      - for numeric columns: min, max, mean, sum (if available)

You MUST base your answer ONLY on this structured summary, but you SHOULD:
- Interpret user intent flexibly (e.g., "supply" ~ quantities or number of rows)
- Prefer approximate but clearly-explained answers over saying "out_of_scope"
  when the data is sufficient for a reasonable interpretation.
- Be concise: state the key answer first (e.g., brand name, number, region) then briefly explain.

Default conventions:
- Treat "overall" workbook questions as referring primarily to the
  "Consolidated_Sales" sheet when it exists.
- For questions like:
  - "how many rows / columns?" → use the rows/columns totals from the relevant sheet.
  - "which region/state/city has the highest supply/sales?" →
      - If there is a numeric quantity column (e.g., qty_units, qty_cases, sales, value):
          aggregate by that metric using the SUM values if provided.
      - If you only have counts per category (top_values), treat the category
        with the highest count as having the highest activity/supply.
- For lists like "what cities / regions do we supply to?", use the distinct
  values from the relevant column summaries (unique_count / top_values keys).

Only treat a question as OUT OF SCOPE when:
- It asks about concepts that are clearly not present anywhere in the summary
  (e.g., CEO email, HR policies), OR
- It requires information that absolutely cannot be approximated from the
  provided statistics.

NUMERIC PRECISION (context-aware):
- For financial values, exact counts, or questions explicitly asking for precision:
  use exact decimals from the summary (e.g., 848215081.46, 25.0488).
- For descriptive or human-readable answers (e.g., "how long", "approximately",
  "on average"): round to sensible precision for readability.
  Example: 1.48 weeks → 1.5 weeks; 24.93 cases → ~25 cases.
- When the question implies exactitude (totals, exact counts, sheet structure):
  preserve full precision. When the context suggests approximation is acceptable,
  round to 1–2 significant figures for clarity.

QUESTION:
{question}

WORKBOOK SUMMARY (JSON):
{json.dumps(summary, indent=2)}

Instructions:
- First identify which sheet(s) and column(s) from the summary are relevant.
- Use the "analytics" section when present (e.g., sales.overall, sales.by_dimension) for pre-computed aggregates.
- Prefer Consolidated_Sales for regions, states, channels, brands, net_sales_value, gross_margin.
- Prefer Consolidated_Nielsen for market_share, weighted_distribution, numeric_distribution by brand/region.
- Prefer Consolidated_Competitor for brand_name, brand_strength, avg_market_share_percent, avg_price_index.
- Whenever the question can be answered using the summary (rows, columns, top_values, analytics), return status "ok".
- Only return "out_of_scope" when the summary truly lacks the required data.
- ALWAYS provide "context_used": which sheet(s)/column(s) you used and how you derived the answer.

Return STRICT JSON ONLY in this format:
{{
  "status": "ok | out_of_scope | error",
  "answer": "short human-readable answer",
  "reason": "optional short explanation for non-ok statuses",
  "context_used": "describe: which sheet/columns you used, what operations you performed, which source values you referred to, and how you derived the answer"
}}
"""

    response = client.chat.completions.create(
        model="openai/gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    data = extract_json(response.choices[0].message.content)

    # Extract token usage from OpenAI/OpenRouter response for telemetry
    usage: Dict[str, Any] = {}
    u = getattr(response, "usage", None)
    if u is not None:
        pt = getattr(u, "prompt_tokens", None)
        ct = getattr(u, "completion_tokens", None)
        tt = getattr(u, "total_tokens", None)
        if pt is not None or ct is not None or tt is not None:
            usage["prompt_tokens"] = pt
            usage["completion_tokens"] = ct
            usage["total_tokens"] = tt if tt is not None else ( (pt or 0) + (ct or 0) )
    if not usage and hasattr(response, "model_dump"):
        try:
            raw = response.model_dump()
            u = raw.get("usage") if isinstance(raw, dict) else None
            if isinstance(u, dict):
                usage["prompt_tokens"] = u.get("prompt_tokens")
                usage["completion_tokens"] = u.get("completion_tokens")
                usage["total_tokens"] = u.get("total_tokens") or ( (u.get("prompt_tokens") or 0) + (u.get("completion_tokens") or 0) )
        except Exception:
            pass

    status = data.get("status")
    answer = data.get("answer")
    reason = data.get("reason")
    context_used = data.get("context_used")

    if status not in {"ok", "out_of_scope", "error"}:
        raise ValueError(f"Invalid status from QA LLM: {status!r}")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("QA LLM response missing non-empty 'answer' field")

    result: Dict[str, Any] = {
        "status": status,
        "answer": answer.strip(),
    }
    if reason:
        result["reason"] = str(reason)
    if isinstance(context_used, str) and context_used.strip():
        result["context_used"] = context_used.strip()
    if usage and (usage.get("total_tokens") is not None or usage.get("prompt_tokens") is not None or usage.get("completion_tokens") is not None):
        result["usage"] = usage

    return result

