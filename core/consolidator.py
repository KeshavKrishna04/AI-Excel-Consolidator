import pandas as pd


def consolidate_domain_data(
    existing_df,
    new_df,
    mapping,
    standard_columns,
    source_file,
    source_sheet,
):
    """
    Applies schema mapping and produces a clean consolidated DataFrame.
    
    Args:
        mapping: dict with {vendor_column: standard_column} format
        standard_columns: list of standard column names to output
    """

    # Define all output columns (standard columns + lineage)
    all_columns = standard_columns + ["source_file", "source_sheet"]
    
    # Invert mapping from {vendor: standard} to {standard: vendor}
    # This makes it easier to look up which vendor column maps to each standard column
    inverted_mapping = {std_col: vendor_col for vendor_col, std_col in mapping.items()}
    
    # 🔒 Always start clean when existing_df is None
    if existing_df is None:
        combined = pd.DataFrame(columns=all_columns)
    else:
        combined = existing_df.copy()

    output_rows = []

    for _, row in new_df.iterrows():
        out_row = {}

        for std_col in standard_columns:
            # Look up which vendor column maps to this standard column
            vendor_col = inverted_mapping.get(std_col)

            if vendor_col and vendor_col in new_df.columns:
                out_row[std_col] = row[vendor_col]
            else:
                out_row[std_col] = None

        # lineage
        out_row["source_file"] = source_file
        out_row["source_sheet"] = source_sheet

        output_rows.append(out_row)

    if not output_rows:
        return combined

    mapped_df = pd.DataFrame(output_rows, columns=all_columns)

    if combined.empty:
        return mapped_df
    else:
        return pd.concat([combined, mapped_df], ignore_index=True)
