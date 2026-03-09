import pandas as pd


def profile_sheet(df: pd.DataFrame, sample_size: int = 8) -> dict:
    """
    Creates a semantic profile of a sheet using BOTH
    column names AND sample values so the mapping AI can infer meaning from values.

    Returns:
        {
          column_name: {
              "dtype": "string/int/float/date",
              "samples": [...],
              "value_hint": "optional short hint for numeric columns (e.g. range, percentage-like)"
          }
        }
    """
    profile = {}

    for col in df.columns:
        series = df[col].dropna()

        samples = series.astype(str).head(sample_size).tolist()

        entry = {
            "dtype": str(series.dtype),
            "samples": samples,
        }

        # Add value hint for numeric columns to help AI map e.g. price_differential_* → *_share
        try:
            numeric = pd.to_numeric(series, errors="coerce").dropna()
            if len(numeric) > 0:
                lo, hi = float(numeric.min()), float(numeric.max())
                if 0 <= lo and hi <= 100 and hi > 1:
                    entry["value_hint"] = f"numeric, range {lo:.0f}-{hi:.0f} (percentage/share-like)"
                else:
                    entry["value_hint"] = f"numeric, range {lo:.0f}-{hi:.0f}"
        except Exception:
            pass

        profile[col] = entry

    return profile

