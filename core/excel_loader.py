import pandas as pd


def load_excel_sheets(path: str):
    """
    Loads all non-empty sheets from an Excel file.

    Returns:
        List of tuples: (sheet_name, DataFrame)
    """
    try:
        sheets_dict = pd.read_excel(path, sheet_name=None)
    except Exception as e:
        raise ValueError(f"Failed to read Excel file {path}: {e}")

    results = []

    for sheet_name, df in sheets_dict.items():
        # Guard: must be a DataFrame
        if not isinstance(df, pd.DataFrame):
            continue

        # Skip empty sheets
        if df.empty:
            continue

        # Normalize column names (trim only, NO renaming)
        df.columns = [str(c).strip() for c in df.columns]

        results.append((sheet_name, df))

    if not results:
        raise ValueError(f"No usable sheets found in {path}")

    return results
