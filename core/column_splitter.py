import pandas as pd
import re


def parse_combined_value(value, format_spec):
    """
    Parse a combined column value based on format specification.
    
    Args:
        value: The combined value (e.g., "(Big Bazaar, CUST_001)")
        format_spec: Format description like "(customer_name,customer_code)"
    
    Returns:
        Dictionary with parsed values: {target_col: parsed_value}
    """
    if pd.isna(value) or value is None:
        return {}
    
    value_str = str(value).strip()
    
    if not value_str:
        return {}
    
    # Extract format pattern from format_spec
    # Format spec examples: "(customer_name,customer_code)", "(value1,value2)"
    # Extract the pattern inside parentheses
    format_match = re.search(r'\(([^)]+)\)', format_spec)
    if format_match:
        # Format is like "(value1,value2)"
        pattern = r'\(([^,]+),([^)]+)\)'
        match = re.match(pattern, value_str)
        if match:
            return {
                "value1": match.group(1).strip(),
                "value2": match.group(2).strip()
            }
    else:
        # Try to extract pattern from format_spec directly
        # Look for comma-separated pattern
        if ',' in format_spec:
            # Try comma-separated format
            parts = value_str.split(',')
            if len(parts) >= 2:
                return {
                    "value1": parts[0].strip(),
                    "value2": parts[1].strip()
                }
    
    # Try common patterns
    # Pattern 1: (value1,value2)
    paren_match = re.match(r'\(([^,]+),([^)]+)\)', value_str)
    if paren_match:
        return {
            "value1": paren_match.group(1).strip(),
            "value2": paren_match.group(2).strip()
        }
    
    # Pattern 2: value1,value2 (comma-separated)
    if ',' in value_str:
        parts = value_str.split(',', 1)
        if len(parts) == 2:
            return {
                "value1": parts[0].strip(),
                "value2": parts[1].strip()
            }
    
    # Pattern 3: value1|value2 (pipe-separated)
    if '|' in value_str:
        parts = value_str.split('|', 1)
        if len(parts) == 2:
            return {
                "value1": parts[0].strip(),
                "value2": parts[1].strip()
            }
    
    # If no pattern matches, return empty dict
    return {}


def apply_column_splits(df, splits_config):
    """
    Apply column splitting operations to a DataFrame.
    
    Args:
        df: Source DataFrame
        splits_config: Dictionary with split configurations:
            {
                "vendor_column": {
                    "format": "format description",
                    "targets": ["target_col1", "target_col2"]
                }
            }
    
    Returns:
        DataFrame with split columns added (original columns preserved)
    """
    df = df.copy()
    
    for vendor_col, split_info in splits_config.items():
        if vendor_col not in df.columns:
            continue
        
        format_spec = split_info.get("format", "")
        targets = split_info.get("targets", [])
        
        if len(targets) < 2:
            continue  # Need at least 2 target columns
        
        print(f"      Splitting '{vendor_col}' -> {targets}")
        
        # Parse each value in the vendor column
        parsed_values = df[vendor_col].apply(
            lambda x: parse_combined_value(x, format_spec)
        )
        
        # Extract values into target columns
        for idx, target in enumerate(targets):
            if idx == 0:
                key = "value1"
            elif idx == 1:
                key = "value2"
            else:
                # For more than 2 targets, try to split further
                key = f"value{idx+1}"
            
            # Extract the value for this target
            df[target] = parsed_values.apply(
                lambda pv: pv.get(key, None) if isinstance(pv, dict) and key in pv else None
            )
        
        # Count successful splits
        successful_splits = parsed_values.apply(lambda pv: len(pv) > 0).sum()
        print(f"        Successfully split {successful_splits}/{len(df)} values")
    
    return df
