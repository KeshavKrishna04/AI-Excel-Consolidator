from typing import Any, Dict, List, Optional, TypedDict

import os
import pandas as pd
from langgraph.graph import END, StateGraph

from agents.schema_agent import profile_sheet
from agents.domain_agent import detect_domain
from agents.mapping_agent import generate_schema_mapping
from agents.validation_agent import validate_sheet
from core.column_splitter import apply_column_splits
from core.consolidator import consolidate_domain_data


class SheetState(TypedDict, total=False):
    """Shared state for processing a single sheet through the LangGraph workflow."""

    sheet_name: str
    df: pd.DataFrame
    profile: Dict[str, Any]
    domain_info: Dict[str, Any]
    domain: Optional[str]
    schemas: Dict[str, List[str]]
    mapping_result: Dict[str, Any]
    mapping: Dict[str, str]
    splits_config: Dict[str, Any]
    df_to_consolidate: pd.DataFrame
    validation: Dict[str, Any]
    consolidated: Dict[str, Optional[pd.DataFrame]]
    source_file: str
    source_sheet: str


def _profile_node(state: SheetState) -> SheetState:
    sheet_name = state["sheet_name"]
    print(f"    Profiling sheet: {sheet_name}")
    profile = profile_sheet(state["df"])
    return {"profile": profile}


def _detect_domain_node(state: SheetState) -> SheetState:
    sheet_name = state["sheet_name"]
    df = state["df"]
    profile = state["profile"]

    domain_info = detect_domain(
        sheet_name=sheet_name,
        column_names=list(df.columns),
        profile=profile,
    )
    domain = domain_info.get("domain")

    print(f"    Detected domain: {domain}")

    return {
        "domain_info": domain_info,
        "domain": domain,
    }


def _route_on_domain(state: SheetState) -> str:
    domain = state.get("domain")
    schemas = state.get("schemas") or {}

    if not domain or domain not in schemas:
        print(f"    Unsupported domain: {domain}")
        return "unsupported"

    return "continue"


def _generate_mapping_node(state: SheetState) -> SheetState:
    domain = state["domain"]
    schemas = state["schemas"]
    profile = state["profile"]

    standard_columns = schemas[domain]  # type: ignore[index]

    mapping_result = generate_schema_mapping(
        profile=profile,
        standard_columns=standard_columns,
        domain=domain,
    )

    mapping = mapping_result.get("mapping", {})
    splits_config = mapping_result.get("splits", {})

    print(f"    Mapping: {len(mapping)} columns mapped")
    if splits_config:
        print(
            f"    Splits detected: {len(splits_config)} combined column(s) to split"
        )

    return {
        "mapping_result": mapping_result,
        "mapping": mapping,
        "splits_config": splits_config,
    }


def _apply_splits_node(state: SheetState) -> SheetState:
    df = state["df"]
    mapping = dict(state["mapping"])
    splits_config = state.get("splits_config") or {}
    profile = state["profile"]

    df_to_consolidate = df

    if splits_config:
        print("    Applying column splits...")
        df_to_consolidate = apply_column_splits(df_to_consolidate, splits_config)

        for vendor_col, split_info in splits_config.items():
            targets = split_info.get("targets", [])

            if vendor_col in mapping:
                removed_mapping = mapping.pop(vendor_col)
                print(f"      Removed mapping: {vendor_col} -> {removed_mapping}")

            for target_col in targets:
                if target_col in df_to_consolidate.columns:
                    mapping[target_col] = target_col
                    print(f"      Added mapping: {target_col} -> {target_col}")
                else:
                    print(
                        f"      Warning: Split target column '{target_col}' "
                        "not found in DataFrame"
                    )

        profile = profile_sheet(df_to_consolidate)

    return {
        "df_to_consolidate": df_to_consolidate,
        "mapping": mapping,
        "profile": profile,
    }


def _validate_node(state: SheetState) -> SheetState:
    domain = state["domain"]
    profile = state["profile"]
    mapping = state["mapping"]

    validation = validate_sheet(
        profile=profile,
        mapping=mapping,
        domain=domain,  # type: ignore[arg-type]
    )

    if not validation.get("accept", False):
        print(f"    Skipping sheet: {validation.get('reason', 'no reason provided')}")

    return {"validation": validation}


def _route_on_validation(state: SheetState) -> str:
    validation = state.get("validation") or {}
    return "accept" if validation.get("accept") else "reject"


def _consolidate_node(state: SheetState) -> SheetState:
    domain = state["domain"]
    schemas = state["schemas"]
    consolidated = dict(state.get("consolidated") or {})
    df_to_consolidate = (
        state["df_to_consolidate"]
        if "df_to_consolidate" in state
        else state["df"]
    )

    standard_columns = schemas[domain]  # type: ignore[index]

    existing_df = consolidated.get(domain)

    source_file = state["source_file"]
    source_sheet = state["source_sheet"]

    updated_df = consolidate_domain_data(
        existing_df=existing_df,
        new_df=df_to_consolidate,
        mapping=state["mapping"],
        standard_columns=standard_columns,
        source_file=os.path.basename(source_file),
        source_sheet=source_sheet,
    )

    consolidated[domain] = updated_df

    print(f"    Consolidated: {len(updated_df)} total rows for {domain}")

    return {"consolidated": consolidated}


def build_sheet_graph():
    """
    Build a LangGraph workflow that encapsulates the per-sheet AI pipeline:
    - profile
    - domain detection
    - schema mapping
    - optional column splitting
    - semantic validation
    - consolidation into the running domain DataFrames
    """
    workflow = StateGraph(SheetState)

    workflow.add_node("profile", _profile_node)
    workflow.add_node("detect_domain", _detect_domain_node)
    workflow.add_node("generate_mapping", _generate_mapping_node)
    workflow.add_node("apply_splits", _apply_splits_node)
    workflow.add_node("validate", _validate_node)
    workflow.add_node("consolidate", _consolidate_node)

    workflow.set_entry_point("profile")
    workflow.add_edge("profile", "detect_domain")

    workflow.add_conditional_edges(
        "detect_domain",
        _route_on_domain,
        {
            "unsupported": END,
            "continue": "generate_mapping",
        },
    )

    workflow.add_edge("generate_mapping", "apply_splits")
    workflow.add_edge("apply_splits", "validate")

    workflow.add_conditional_edges(
        "validate",
        _route_on_validation,
        {
            "accept": "consolidate",
            "reject": END,
        },
    )

    workflow.add_edge("consolidate", END)

    return workflow.compile()

