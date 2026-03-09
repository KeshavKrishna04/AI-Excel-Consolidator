import os
import pandas as pd


def write_excel(df, path):
    """
    Write DataFrame to Excel file.
    Handles file locking by removing existing file if locked.
    """
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    # Remove existing file if it exists (handles locked files)
    if os.path.exists(path):
        try:
            os.remove(path)
        except PermissionError:
            # File might be open, try to write with different name
            raise PermissionError(
                f"Cannot write to {path}. Please close the file if it's open in Excel."
            )
    
    # Write the DataFrame
    df.to_excel(path, index=False, engine='openpyxl')


def write_multisheet_excel(dataframes_dict, path):
    """
    Write multiple DataFrames to a single Excel file with multiple sheets.
    
    Args:
        dataframes_dict: Dictionary with {sheet_name: DataFrame}
        path: Output file path
    """
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    # Remove existing file if it exists
    if os.path.exists(path):
        try:
            os.remove(path)
        except PermissionError:
            raise PermissionError(
                f"Cannot write to {path}. Please close the file if it's open in Excel."
            )
    
    # Write all sheets to single Excel file
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        for sheet_name, df in dataframes_dict.items():
            if df is not None and not df.empty:
                # Excel sheet name limitations: max 31 chars, no special chars like : \ / ? * [ ]
                # Replace invalid characters and truncate if needed
                safe_sheet_name = sheet_name[:31].replace(':', '_').replace('\\', '_').replace('/', '_').replace('?', '_').replace('*', '_').replace('[', '_').replace(']', '_')
                df.to_excel(writer, sheet_name=safe_sheet_name, index=False)
