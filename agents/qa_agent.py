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

    prompt = f"""
You are a senior data analyst AI answering questions about an Excel workbook
that contains consolidated business data (sales, nielsen, pricing, competitor, baseline).

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
~- It requires information that absolutely cannot be approximated from the
  provided statistics.

QUESTION:
{question}

WORKBOOK SUMMARY (JSON):
{json.dumps(summary, indent=2)}

Instructions:
- Think carefully about which sheet(s) and column(s) are relevant.
- Prefer using the 'Consolidated_Sales' sheet for questions about regions,
  states, cities, customers, quantities, and sales values.
- Whenever the question can be answered using row counts, column counts,
  unique counts, top_values, or numeric aggregates, you MUST answer it
  with status "ok" and a clear explanation.
- Only when none of the sheets/columns can reasonably address the question
  should you return "out_of_scope".
- For unexpected internal issues, use status "error" and a short reason.

Return STRICT JSON ONLY in this format:
{{
  "status": "ok | out_of_scope | error",
  "answer": "short human-readable answer",
  "reason": "optional short explanation for non-ok statuses"
}}
"""

    response = client.chat.completions.create(
        model="openai/gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    data = extract_json(response.choices[0].message.content)

    status = data.get("status")
    answer = data.get("answer")
    reason = data.get("reason")

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

    return result

