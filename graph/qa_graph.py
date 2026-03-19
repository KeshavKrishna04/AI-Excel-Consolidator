from typing import Any, Dict, Optional, TypedDict, Tuple

import os
from pathlib import Path
import pandas as pd
from langgraph.graph import END, StateGraph

from agents.qa_agent import answer_question_over_summary
from utils.cache_utils import find_similar_cache, load_cache, now_iso, save_checkpoint


class QAState(TypedDict, total=False):
    """Shared state for the Q&A LangGraph workflow."""

    # Input
    question: str
    workbook_path: str

    # Intermediate
    summary: Dict[str, Any]
    _cache_hit: bool  # Internal: True when cache returned answer, skip pipeline
    source: str  # "cached" (newly stored) | "reused" (served from cache) | ""
    source_file: str  # detected dataset file name (e.g., "volta.clean")
    cache_lookup_seconds: float  # time spent in cache lookup

    # Output
    answer: str
    status: str
    reason: Optional[str]
    context_used: Optional[str]  # Agent's explanation of sources and reasoning
    usage: Optional[Dict[str, Any]]  # LLM token usage for telemetry


SUPPORTED_DATASET_EXT: Tuple[str, ...] = (".xlsx", ".csv", ".txt", ".clean")


def _pick_first_supported_file(folder: Path) -> Path:
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Dataset folder not found: {folder}")

    candidates: list[Path] = []
    for name in os.listdir(folder):
        p = folder / name
        if p.is_file() and p.suffix.lower() in SUPPORTED_DATASET_EXT:
            try:
                if p.stat().st_size == 0:
                    continue
            except OSError:
                continue
            candidates.append(p)

    if candidates:
        # Prefer the most recently modified supported dataset file.
        ranked = []
        for p in candidates:
            try:
                ranked.append((float(p.stat().st_mtime), p.name.lower(), p))
            except OSError:
                continue
        if ranked:
            ranked.sort(key=lambda t: (t[0], t[1]), reverse=True)
            return ranked[0][2]

    raise FileNotFoundError(
        f"No supported dataset found in: {folder}. "
        f"Expected one of: {', '.join(SUPPORTED_DATASET_EXT)}"
    )


def _resolve_dataset_path(raw: str) -> Path:
    """
    Resolve dataset path from the provided workbook_path:
    - If it's an existing file: use it.
    - If it's an existing directory: pick first supported file inside it.
    - If it doesn't exist: fall back to scanning ./outputs (keeps benchmark stable).
    """
    p = Path(raw)
    if p.exists():
        return p if p.is_file() else _pick_first_supported_file(p)
    return _pick_first_supported_file(Path("outputs"))


def _summarize_workbook_node(state: QAState) -> QAState:
    """
    Load a dataset file and build a compact, JSON-serializable summary the LLM
    can reason over.

    Supported formats:
    - .xlsx: existing multi-sheet Excel summarization (unchanged)
    - .csv: treated as a single-sheet table
    - .txt/.clean: treated as unstructured text context
    """
    dataset_path = _resolve_dataset_path(state["workbook_path"])
    suffix = dataset_path.suffix.lower()

    # ---------------------------
    # Unstructured text datasets
    # ---------------------------
    if suffix in {".txt", ".clean"}:
        try:
            text_data = dataset_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text_data = dataset_path.read_text(encoding="utf-8", errors="replace")
        if not text_data.strip():
            raise ValueError(f"Dataset file is empty: {dataset_path}")
        # Return the full document text. The QA agent is responsible for scanning
        # it safely (e.g., chunking) to respect model context limits.
        return {
            "summary": {
                "text_data": text_data,
                "source_file": dataset_path.name,
            }
        }

    # ---------------------------
    # Structured tabular datasets
    # ---------------------------
    sheets: Dict[str, pd.DataFrame]
    if suffix == ".xlsx":
        # Read all sheets into a dict of DataFrames (existing behavior)
        sheets = pd.read_excel(str(dataset_path), sheet_name=None)
    elif suffix == ".csv":
        df = pd.read_csv(str(dataset_path))
        sheets = {dataset_path.stem: df}
    else:
        raise ValueError(
            f"Unsupported dataset extension: {dataset_path.suffix} "
            f"(supported: {', '.join(supported_ext)})"
        )

    if not sheets:
        raise ValueError("Dataset is empty (no sheets found).")

    summary: Dict[str, Any] = {
        "sheets": {},
        "analytics": {},
    }
    summary["source_file"] = dataset_path.name

    # ---------- Per-sheet structural summary ----------
    for sheet_name, df in sheets.items():
        total_rows = int(df.shape[0])
        total_cols = int(df.shape[1])

        sheet_info: Dict[str, Any] = {
            "rows": total_rows,
            "columns": total_cols,
            "column_summaries": {},
        }

        # Build per-column lightweight summaries
        for col in df.columns:
            series = df[col]
            col_summary: Dict[str, Any] = {
                "dtype": str(series.dtype),
            }

            # Always include basic cardinality information
            non_null = series.dropna()
            col_summary["non_null_count"] = int(non_null.shape[0])
            col_summary["unique_count"] = int(non_null.nunique(dropna=True))

            # Categorical / string-like: list top values and counts (truncated)
            if series.dtype == "object" or series.dtype.name == "category":
                value_counts = (
                    non_null.astype(str).value_counts()
                )
                max_categories = 30
                top_values: Dict[str, Any] = {}
                for value, count in value_counts.iloc[:max_categories].items():
                    top_values[str(value)] = int(count)
                col_summary["top_values"] = top_values
                if value_counts.shape[0] > max_categories:
                    col_summary["top_values_truncated"] = True

            else:
                # Numeric / datetime: basic stats
                numeric = pd.to_numeric(series, errors="coerce")
                if numeric.notna().any():
                    col_summary["min"] = float(numeric.min())
                    col_summary["max"] = float(numeric.max())
                    col_summary["mean"] = float(numeric.mean())
                    col_summary["sum"] = float(numeric.sum())

            sheet_info["column_summaries"][str(col)] = col_summary

        summary["sheets"][str(sheet_name)] = sheet_info

    # ---------- Higher-level analytics for deeper reasoning ----------

    analytics: Dict[str, Any] = {}

    # Helper to find a sheet by a keyword (e.g., "sales", "nielsen")
    def _find_sheet_name(keyword: str) -> Optional[str]:
        keyword_lower = keyword.lower()
        for name in sheets.keys():
            name_str = str(name)
            if keyword_lower in name_str.lower():
                return name_str
        return None

    # Helper to detect a numeric column by substrings in its name
    def _find_numeric_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
        lowered = [c.lower() for c in candidates]
        for col in df.columns:
            col_l = str(col).lower()
            if any(key in col_l for key in lowered):
                series = df[col]
                numeric = pd.to_numeric(series, errors="coerce")
                if numeric.notna().any():
                    return str(col)
        return None

    # Helper to aggregate by a categorical dimension (e.g., state, city, region, brand)
    def _dimension_stats(
        df: pd.DataFrame,
        dim_col: str,
        qty_col: Optional[str],
        value_col: Optional[str],
        margin_col: Optional[str],
    ) -> Dict[str, Any]:
        if dim_col not in df.columns:
            return {}

        result: Dict[str, Any] = {}
        grouped = df.groupby(dim_col, dropna=True)

        # Row counts per category
        result["row_count"] = {
            str(idx): int(count) for idx, count in grouped.size().items()
        }

        # Aggregate key numeric metrics when available
        if qty_col and qty_col in df.columns:
            qty_series = pd.to_numeric(df[qty_col], errors="coerce")
            result["sum_quantity"] = {
                str(idx): float(val)
                for idx, val in grouped[qty_col].apply(
                    lambda s: pd.to_numeric(s, errors="coerce").sum()
                ).items()
            }
        if value_col and value_col in df.columns:
            result["sum_value"] = {
                str(idx): float(val)
                for idx, val in grouped[value_col].apply(
                    lambda s: pd.to_numeric(s, errors="coerce").sum()
                ).items()
            }
        if margin_col and margin_col in df.columns:
            result["sum_margin"] = {
                str(idx): float(val)
                for idx, val in grouped[margin_col].apply(
                    lambda s: pd.to_numeric(s, errors="coerce").sum()
                ).items()
            }

        return result

    # ----- Sales analytics (used by many of the user's questions) -----
    sales_sheet_name = _find_sheet_name("Consolidated_Sales") or _find_sheet_name(
        "sales"
    )
    if sales_sheet_name is not None:
        sales_df = sheets[sales_sheet_name]
        sales_analytics: Dict[str, Any] = {
            "sheet_name": sales_sheet_name,
            "overall": {},
            "by_dimension": {},
            "correlations": {},
            "time": {},
        }

        # Detect candidate metric columns
        qty_col = _find_numeric_column(
            sales_df, ["qty", "quantity", "volume", "cases", "units"]
        )
        value_col = _find_numeric_column(
            sales_df, ["net_sales", "nsv", "sales_value", "value", "revenue"]
        )
        discount_col = _find_numeric_column(
            sales_df, ["disc", "discount", "promo"]
        )
        margin_col = _find_numeric_column(sales_df, ["margin"])

        sales_analytics["metric_columns"] = {
            "quantity": qty_col,
            "value": value_col,
            "discount": discount_col,
            "margin": margin_col,
        }

        # Overall aggregates for the whole sheet
        if qty_col and qty_col in sales_df.columns:
            qty_numeric = pd.to_numeric(sales_df[qty_col], errors="coerce")
            sales_analytics["overall"]["total_quantity"] = float(
                qty_numeric.sum(skipna=True)
            )
            sales_analytics["overall"]["average_quantity"] = float(
                qty_numeric.mean(skipna=True)
            )
            sales_analytics["overall"]["median_quantity"] = float(
                qty_numeric.median(skipna=True)
            )
            sales_analytics["overall"]["max_quantity"] = float(
                qty_numeric.max(skipna=True)
            )

        if value_col and value_col in sales_df.columns:
            value_numeric = pd.to_numeric(sales_df[value_col], errors="coerce")
            sales_analytics["overall"]["total_value"] = float(
                value_numeric.sum(skipna=True)
            )
            sales_analytics["overall"]["average_value"] = float(
                value_numeric.mean(skipna=True)
            )

        if discount_col and discount_col in sales_df.columns:
            disc_numeric = pd.to_numeric(sales_df[discount_col], errors="coerce")
            sales_analytics["overall"]["average_discount"] = float(
                disc_numeric.mean(skipna=True)
            )
            sales_analytics["overall"]["discount_non_null_fraction"] = float(
                disc_numeric.notna().mean()
            )

        # Per-dimension breakdowns: brand, state, city, region, channel, pack_type, category, promotion_type
        dimension_candidates = [
            "brand",
            "brand_name",
            "state",
            "city",
            "region",
            "channel",
            "pack_type",
            "packtype",
            "category",
            "promotion_type",
        ]

        by_dimension: Dict[str, Any] = {}
        for candidate in dimension_candidates:
            for col in sales_df.columns:
                if str(col).lower() == candidate:
                    stats = _dimension_stats(
                        sales_df, str(col), qty_col, value_col, margin_col
                    )
                    if stats:
                        by_dimension[str(col)] = stats
                    break
        sales_analytics["by_dimension"] = by_dimension

        # Simple correlation diagnostics between discount and quantity / value
        correlations: Dict[str, Any] = {}
        if discount_col and discount_col in sales_df.columns:
            disc = pd.to_numeric(sales_df[discount_col], errors="coerce")
            if qty_col and qty_col in sales_df.columns:
                qty_series = pd.to_numeric(sales_df[qty_col], errors="coerce")
                corr = disc.corr(qty_series)
                if pd.notna(corr):
                    correlations["discount_vs_quantity"] = float(corr)
            if value_col and value_col in sales_df.columns:
                value_series = pd.to_numeric(sales_df[value_col], errors="coerce")
                corr = disc.corr(value_series)
                if pd.notna(corr):
                    correlations["discount_vs_value"] = float(corr)
        sales_analytics["correlations"] = correlations

        # Basic monthly roll-up if a date-like column exists
        date_col = None
        for col in sales_df.columns:
            try:
                parsed = pd.to_datetime(sales_df[col], errors="coerce", dayfirst=True)
                if parsed.notna().mean() > 0.5:
                    date_col = str(col)
                    break
            except Exception:
                continue

        if date_col:
            parsed_dates = pd.to_datetime(
                sales_df[date_col], errors="coerce", dayfirst=True
            )
            month_series = parsed_dates.dt.to_period("M").astype(str)
            month_counts = month_series.value_counts().sort_index()
            sales_analytics["time"]["transactions_by_month"] = {
                str(idx): int(count) for idx, count in month_counts.items()
            }

        analytics["sales"] = sales_analytics

    # ----- Nielsen / cross-sheet brand analytics (for cross-sheet questions) -----
    nielsen_sheet_name = _find_sheet_name("Consolidated_Nielsen") or _find_sheet_name(
        "nielsen"
    )
    if nielsen_sheet_name is not None:
        nielsen_df = sheets[nielsen_sheet_name]
        nielsen_analytics: Dict[str, Any] = {
            "sheet_name": nielsen_sheet_name,
            "by_brand": {},
        }

        # Detect brand column and a numeric sales metric in Nielsen sheet
        nielsen_brand_col: Optional[str] = None
        for col in nielsen_df.columns:
            if "brand" in str(col).lower():
                nielsen_brand_col = str(col)
                break

        nielsen_value_col = _find_numeric_column(
            nielsen_df, ["brand_sales", "sales_inr", "sales_value", "value", "revenue"]
        )

        if nielsen_brand_col and nielsen_value_col:
            grouped = nielsen_df.groupby(nielsen_brand_col, dropna=True)
            brand_stats: Dict[str, Any] = {}
            # Row counts and total Nielsen sales per brand
            counts = grouped.size()
            sums = grouped[nielsen_value_col].apply(
                lambda s: pd.to_numeric(s, errors="coerce").sum()
            )
            for brand in counts.index:
                key = str(brand)
                brand_stats[key] = {
                    "row_count": int(counts.loc[brand]),
                    "nielsen_sales_value": float(sums.loc[brand]),
                }
            nielsen_analytics["by_brand"] = brand_stats

        analytics["nielsen"] = nielsen_analytics

        # If we also have sales analytics, build a simple cross-sheet comparison by brand
        if "sales" in analytics:
            sales_df = sheets[sales_sheet_name] if sales_sheet_name else None
            if sales_df is not None:
                sales_brand_col: Optional[str] = None
                for col in sales_df.columns:
                    if "brand" in str(col).lower():
                        sales_brand_col = str(col)
                        break

                sales_value_col = analytics["sales"]["metric_columns"].get("value")

                if sales_brand_col and sales_value_col and sales_value_col in sales_df.columns:
                    sales_grouped = sales_df.groupby(sales_brand_col, dropna=True)
                    sales_sums = sales_grouped[sales_value_col].apply(
                        lambda s: pd.to_numeric(s, errors="coerce").sum()
                    )

                    cross_brand: Dict[str, Any] = {}
                    for brand in set(sales_sums.index).intersection(
                        nielsen_analytics.get("by_brand", {}).keys()
                    ):
                        brand_key = str(brand)
                        sales_val = float(sales_sums.loc[brand])
                        nielsen_entry = nielsen_analytics["by_brand"][brand_key]
                        nielsen_val = float(
                            nielsen_entry.get("nielsen_sales_value", 0.0)
                        )
                        cross_brand[brand_key] = {
                            "sales_value": sales_val,
                            "nielsen_sales_value": nielsen_val,
                            "difference": sales_val - nielsen_val,
                        }

                    analytics["cross_brand_sales_vs_nielsen"] = cross_brand

    summary["analytics"] = analytics

    return {"summary": summary}


def _answer_question_node(state: QAState) -> QAState:
    """Use the LLM-based QA agent to answer the user's question."""
    question = state["question"]
    summary = state["summary"]

    result = answer_question_over_summary(question=question, summary=summary)

    out: QAState = {
        "answer": result.get("answer", ""),
        "status": result.get("status", "error"),
        "reason": result.get("reason"),
    }
    ctx = result.get("context_used")
    if isinstance(ctx, str) and ctx.strip():
        out["context_used"] = ctx.strip()

    # Propagate LLM usage to the state so downstream evaluation can see token counts.
    usage = result.get("usage")
    if isinstance(usage, dict) and usage:
        out["usage"] = usage

    return out


def _is_sales_only_query(question: str) -> bool:
    """True if the question relates only to Consolidated_Sales (not Nielsen, Pricing, etc)."""
    q = (question or "").lower()
    if not q:
        return False
    other_sheets = ["nielsen", "pricing", "competitor", "baseline"]
    if any(s in q for s in other_sheets):
        return False
    return "sales" in q or "consolidated_sales" in q


def _check_cache_node(state: QAState) -> QAState:
    """
    Generic cache lookup for any supported dataset type.
    If cache hit, return cached answer and _cache_hit=True to skip the full pipeline.
    """
    import time

    question = state.get("question") or ""
    try:
        dataset_path = _resolve_dataset_path(state.get("workbook_path", "outputs"))
        source_file = dataset_path.name
    except Exception:
        source_file = ""

    t0 = time.perf_counter()
    entries = load_cache()
    match = find_similar_cache(question, entries, source_file=source_file or None)
    lookup_elapsed = time.perf_counter() - t0

    if match is not None and str(match.get("answer") or "").strip():
        print("CACHE HIT")
        return {
            **_state_to_dict(state),
            "answer": str(match.get("answer") or "").strip(),
            "status": "ok",
            "context_used": "[reused]",
            "_cache_hit": True,
            "source": "reused",
            "source_file": source_file,
            "cache_lookup_seconds": float(lookup_elapsed),
        }

    print("CACHE MISS")
    return {
        **_state_to_dict(state),
        "_cache_hit": False,
        "source": "",
        "source_file": source_file,
        "cache_lookup_seconds": float(lookup_elapsed),
    }


def _checkpoint_node(state: QAState) -> QAState:
    """
    Append a minimal checkpoint entry for any supported dataset type.
    Runs only when we have question + answer and the result was not reused.
    """
    question = state.get("question") or ""
    answer = state.get("answer") or ""
    if not question or not answer:
        return state
    if state.get("source") == "reused":
        return state

    summary = state.get("summary") or {}
    source_file = state.get("source_file") or str(summary.get("source_file") or "")

    tables_used = []
    if isinstance(summary, dict) and "sheets" in summary and isinstance(summary.get("sheets"), dict):
        tables_used = list(summary["sheets"].keys())[:10]
    elif source_file:
        tables_used = [source_file]

    entry = {
        "question": question[:1000],
        "tables_used": tables_used,
        "answer": answer[:2000],
        "timestamp": now_iso(),
        "source_file": source_file,
    }
    save_checkpoint(entry)
    print("[checkpoint] written")
    return {**_state_to_dict(state), "source": "cached"}


def _state_to_dict(state: QAState) -> Dict[str, Any]:
    """Turn TypedDict state into a plain dict for merging."""
    return dict(state) if isinstance(state, dict) else {}


def _route_after_cache(state: QAState) -> str:
    if state.get("_cache_hit"):
        return END
    return "summarize_workbook"


def _route_after_answer(state: QAState) -> str:
    # Always checkpoint after answering (all dataset types).
    # Cache hits never reach this node, so we won't duplicate log entries.
    return "checkpoint"


def build_qa_graph():
    """
    Build a LangGraph workflow that:
    - loads and summarizes the consolidated_output.xlsx workbook
    - uses an LLM to answer a natural-language question over that summary
    """
    workflow = StateGraph(QAState)

    workflow.add_node("check_cache", _check_cache_node)
    workflow.add_node("summarize_workbook", _summarize_workbook_node)
    workflow.add_node("answer_question", _answer_question_node)
    workflow.add_node("checkpoint", _checkpoint_node)

    workflow.set_entry_point("check_cache")
    workflow.add_conditional_edges(
        "check_cache", _route_after_cache, {END: END, "summarize_workbook": "summarize_workbook"}
    )
    workflow.add_edge("summarize_workbook", "answer_question")
    workflow.add_conditional_edges(
        "answer_question", _route_after_answer, {"checkpoint": "checkpoint", END: END}
    )
    workflow.add_edge("checkpoint", END)

    return workflow.compile()

