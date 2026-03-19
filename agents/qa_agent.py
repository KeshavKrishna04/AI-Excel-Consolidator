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

        def _chunk_text(text: str, *, chunk_chars: int = 9000, overlap: int = 500):
            text = text or ""
            if len(text) <= chunk_chars:
                yield (0, text)
                return
            step = max(1, chunk_chars - overlap)
            start = 0
            while start < len(text):
                end = min(len(text), start + chunk_chars)
                yield (start, text[start:end])
                if end >= len(text):
                    break
                start += step

        hits = []

        for start_idx, chunk in _chunk_text(full_text):
            prompt = f"""
You are given a document chunk as context. Your job is to answer the question strictly using this chunk only.

If the answer is not present in this chunk, reply with:
{{"found": false}}

If the answer is present, reply with:
{{
  "found": true,
  "answer": "short answer",
  "evidence": "copy the exact sentence(s) from the chunk that prove the answer"
}}

Question:
{question}

Chunk:
{chunk}
"""
            resp = client.chat.completions.create(
                model="openai/gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            parsed = extract_json(resp.choices[0].message.content)
            if isinstance(parsed, dict) and parsed.get("found") is True:
                ans = str(parsed.get("answer") or "").strip()
                ev = str(parsed.get("evidence") or "").strip()
                if ans:
                    hits.append(
                        {
                            "answer": ans,
                            "evidence": ev,
                            "chunk_start": start_idx,
                        }
                    )

        if not hits:
            return {
                "status": "out_of_scope",
                "answer": "Not found",
                "reason": "The context does not contain the answer.",
                "context_used": "Full document scanned (no matching evidence found).",
            }

        # Synthesize final answer from all chunk-level hits.
        synthesis_prompt = f"""
You are given multiple candidate answers extracted from different chunks of a document.
Choose the best supported answer and return a final response.

Rules:
- Use only the provided candidates/evidence.
- If candidates conflict, prefer the one with the clearest evidence.
- Be concise.

Question:
{question}

CANDIDATES (JSON):
{json.dumps(hits, indent=2, ensure_ascii=False)}

Return STRICT JSON ONLY:
{{
  "status": "ok",
  "answer": "final short answer",
  "context_used": "briefly cite the evidence used"
}}
"""
        response = client.chat.completions.create(
            model="openai/gpt-4o",
            messages=[{"role": "user", "content": synthesis_prompt}],
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

