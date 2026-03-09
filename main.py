import os
import pandas as pd

from core.excel_loader import load_excel_sheets
from core.standard_parser import extract_standard_schemas
from core.consolidator import consolidate_domain_data
from core.excel_writer import write_excel, write_multisheet_excel
from core.column_splitter import apply_column_splits

from agents.domain_agent import detect_domain
from agents.schema_agent import profile_sheet
from agents.mapping_agent import generate_schema_mapping
from agents.validation_agent import validate_sheet
from agents.enrichment_agent import enrich_state_from_city
from graph.sheet_graph import build_sheet_graph

DATA_DIR = "data"
OUTPUT_DIR = "outputs"

# ✅ STANDARD FILES (EXPLICIT, NO GUESSING)
STANDARD_FILES = {
    "sales": "data/sales.xlsx",
    "nielsen": "data/nielsen.xlsx",
    "pricing": "data/pricing.xlsx",
    "competitor": "data/competitor.xlsx",
    "baseline": "data/baseline.xlsx",
}

os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_all_standard_schemas():
    """
    Loads standard schemas from individual standard files.
    Returns: dict(domain -> ordered list of columns)
    """
    schemas = {}

    for domain, path in STANDARD_FILES.items():
        if not os.path.exists(path):
            raise FileNotFoundError(f"Standard file missing: {path}")

        extracted_schemas = extract_standard_schemas(path)

        # If the domain is directly in the extracted schemas, use it
        # Otherwise, use the first schema found (handles single-sheet files like "Sheet1")
        if domain in extracted_schemas:
            schemas[domain] = extracted_schemas[domain]
        elif extracted_schemas:
            # Take the first schema (for single-sheet files)
            first_schema_key = list(extracted_schemas.keys())[0]
            schemas[domain] = extracted_schemas[first_schema_key]
        else:
            raise ValueError(
                f"Standard file {path} does not contain any usable schemas"
            )

    return schemas


def run_pipeline(vendor_files):
    # 1️⃣ Load standard schemas
    schemas = load_all_standard_schemas()

    consolidated = {
        "sales": None,
        "nielsen": None,
        "pricing": None,
        "competitor": None,
        "baseline": None,
    }

    # Build LangGraph workflow once and reuse it for every sheet
    sheet_graph = build_sheet_graph()

    for vendor_file in vendor_files:
        print(f"\nProcessing vendor file: {vendor_file}")

        sheets = load_excel_sheets(vendor_file)

        for sheet_name, df in sheets:
            print(f"  Sheet: {sheet_name}")

            if not isinstance(df, pd.DataFrame):
                raise TypeError(
                    f"Expected DataFrame for sheet '{sheet_name}', got {type(df)}"
                )

            # Drive one sheet through the LangGraph workflow.
            # The graph takes care of:
            # - profiling
            # - domain detection
            # - schema mapping
            # - optional column splitting
            # - validation
            # - consolidation into the per-domain DataFrames
            initial_state = {
                "sheet_name": sheet_name,
                "df": df,
                "schemas": schemas,
                "consolidated": consolidated,
                "source_file": vendor_file,
                "source_sheet": sheet_name,
            }

            result_state = sheet_graph.invoke(initial_state)
            consolidated = result_state.get("consolidated", consolidated)

    # 6.5️⃣ ENRICHMENT: Fill state from city (for sales domain)
    if consolidated["sales"] is not None and not consolidated["sales"].empty:
        if "city" in consolidated["sales"].columns and "state" in consolidated["sales"].columns:
            print("\nEnriching state column from city names...")
            consolidated["sales"] = enrich_state_from_city(
                consolidated["sales"], 
                city_column="city", 
                state_column="state"
            )

    # 7️⃣ WRITE OUTPUTS (Single Excel file with multiple sheets)
    print("\n" + "="*60)
    print("WRITING CONSOLIDATED OUTPUTS")
    print("="*60)
    
    # Prepare dataframes for multi-sheet output
    sheets_data = {}
    sheet_names = {
        "sales": "Consolidated_Sales",
        "nielsen": "Consolidated_Nielsen",
        "pricing": "Consolidated_Pricing",
        "competitor": "Consolidated_Competitor",
        "baseline": "Consolidated_Baseline"
    }
    
    for domain, df in consolidated.items():
        if df is None or df.empty:
            print(f"\nSkipping {domain}: No data to consolidate")
            continue
        
        sheets_data[sheet_names[domain]] = df
        print(f"\nPrepared {sheet_names[domain]}: {len(df)} rows, {len(df.columns)} columns")
    
    # Write single Excel file with all sheets
    if sheets_data:
        out_path = os.path.join(OUTPUT_DIR, "consolidated_output.xlsx")
        try:
            print(f"\nWriting consolidated output to: {out_path}")
            write_multisheet_excel(sheets_data, out_path)
            print(f"  Successfully wrote {out_path} with {len(sheets_data)} sheet(s):")
            for sheet_name in sheets_data.keys():
                print(f"    - {sheet_name}")
        except PermissionError as e:
            print(f"  Error: {e}")
            print(f"  Please close the file if it's open in Excel and try again.")
        except Exception as e:
            print(f"  Error writing {out_path}: {e}")
    else:
        # Always emit an output workbook so the UI can still provide a download,
        # even if the AI rejected all sheets or no domains were detected.
        print("\nNo consolidated data to write - all domains were empty or skipped.")
        out_path = os.path.join(OUTPUT_DIR, "consolidated_output.xlsx")
        info_df = pd.DataFrame(
            [
                {
                    "message": "No consolidated sheets were generated.",
                    "hint": "Check logs above: the domain may have been detected as 'unknown' or validation rejected the sheet.",
                }
            ]
        )
        try:
            write_multisheet_excel({"Consolidation_Info": info_df}, out_path)
            print(f"  Wrote info workbook to: {out_path}")
        except Exception as e:
            print(f"  Error writing info workbook {out_path}: {e}")


if __name__ == "__main__":
    # Normalize paths for comparison (handle Windows/Unix path differences)
    STANDARD_NAMES = {os.path.normpath(path) for path in STANDARD_FILES.values()}

    vendor_files = [
        os.path.join(DATA_DIR, f)
        for f in os.listdir(DATA_DIR)
        if (
            f.lower().endswith(".xlsx")
            and os.path.normpath(os.path.join(DATA_DIR, f)) not in STANDARD_NAMES
        )
    ]

    if not vendor_files:
        print("No vendor files found in data/")
    else:
        run_pipeline(vendor_files)
