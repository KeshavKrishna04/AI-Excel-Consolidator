from typing import Any, Dict, Optional, TypedDict

import os
import pandas as pd
from langgraph.graph import END, StateGraph

from agents.qa_agent import answer_question_over_summary


class QAState(TypedDict, total=False):
    """Shared state for the Q&A LangGraph workflow."""

    # Input
    question: str
    workbook_path: str

    # Intermediate
    summary: Dict[str, Any]

    # Output
    answer: str
    status: str
    reason: Optional[str]


def _summarize_workbook_node(state: QAState) -> QAState:
    """
    Load consolidated_output.xlsx and build a compact, JSON-serializable
    summary the LLM can reason over.
    """
    workbook_path = state["workbook_path"]

    if not os.path.exists(workbook_path):
        raise FileNotFoundError(
            f"Consolidated workbook not found at: {workbook_path}. "
            "Run the consolidation pipeline first."
        )

    # Read all sheets into a dict of DataFrames
    sheets = pd.read_excel(workbook_path, sheet_name=None)

    if not sheets:
        raise ValueError("Consolidated workbook is empty (no sheets found).")

    summary: Dict[str, Any] = {
        "sheets": {},
        "analytics": {},
    }

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

    return {
        "answer": result.get("answer", ""),
        "status": result.get("status", "error"),
        "reason": result.get("reason"),
    }


def build_qa_graph():
    """
    Build a LangGraph workflow that:
    - loads and summarizes the consolidated_output.xlsx workbook
    - uses an LLM to answer a natural-language question over that summary
    """
    workflow = StateGraph(QAState)

    workflow.add_node("summarize_workbook", _summarize_workbook_node)
    workflow.add_node("answer_question", _answer_question_node)

    workflow.set_entry_point("summarize_workbook")
    workflow.add_edge("summarize_workbook", "answer_question")
    workflow.add_edge("answer_question", END)

    return workflow.compile()

