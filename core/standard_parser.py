import pandas as pd


def extract_standard_schemas(path: str) -> dict:
    """
    Extract standard schemas from a reference Excel file.

    Supports:
    - Multi-sheet file: each sheet name = domain
    - Single-sheet file: schema returned under key 'single'
      (caller decides domain)
    """
    try:
        xl = pd.ExcelFile(path)
    except Exception as e:
        raise ValueError(f"Failed to open standard file: {e}")

    schemas = {}

    for sheet_name in xl.sheet_names:
        df = xl.parse(sheet_name)

        if df.empty:
            continue

        # Extract column names ONLY (order preserved)
        columns = [str(c).strip() for c in df.columns if str(c).strip()]

        if not columns:
            continue

        schemas[sheet_name.lower()] = columns

    if not schemas:
        raise ValueError("No usable standard schemas found in reference file")

    return schemas
