import json

from llm.openrouter_client import get_llm
from llm.json_utils import extract_json


def generate_schema_mapping(profile: dict, standard_columns: list, domain: str = None) -> dict:
    """
    Uses AI to generate a vendor → standard schema mapping
    using semantic understanding of column names AND values.

    Returns:
        dict: {vendor_column: standard_column} plus optional "splits"
    """

    client = get_llm()

    domain_hint = ""
    if domain:
        domain_hint = f"""
DOMAIN-SPECIFIC (domain={domain}):
- NIELSEN: Map vendor columns that represent competitor/share metrics by POSITION when names differ:
  - price_differential_a, price_differential_b, price_differential_c → competitor_1_share, competitor_2_share, competitor_3_share (a→1, b→2, c→3)
  - Any vendor columns with suffixes _a/_b/_c or _1/_2/_3 that hold numeric share/differential values should map to standard competitor_1_share, competitor_2_share, competitor_3_share in order
- Use VALUES: If profile "samples" show numeric values (e.g. 65, 70, 80) and the standard has *_share columns, treat as share/differential metrics and map by position
- SALES / PRICING / COMPETITOR / BASELINE: Similarly map positional vendor columns (e.g. metric_a, metric_b) to standard columns ending in _1, _2, _3 by order when meaning matches
"""

    prompt = f"""
You are an expert enterprise data-mapping AI. You must infer meaning from BOTH column names AND the example values in the profile.

Vendor sheet semantic profile (column names + dtypes + sample values):
{json.dumps(profile, indent=2)}

AUTHORITATIVE STANDARD schema (DO NOT CHANGE):
{standard_columns}
{domain_hint}

Instructions:
- Map vendor columns to STANDARD columns by MEANING, not just by similar names
- ALWAYS use the "samples" values in the profile to infer meaning (e.g. numeric percentages → *_share; dates → date columns; identifiers → id/code columns)
- When standard has columns like competitor_1_share, competitor_2_share, competitor_3_share, look for vendor columns that represent the same concept with different names (e.g. price_differential_a/b/c, competitor_share_a/b/c) and map by POSITION: first → _1, second → _2, third → _3
- Use ONLY standard column names as targets
- DO NOT invent columns
- Partial mappings are allowed; unmapped standard columns will be left empty
- Missing standard columns will be handled downstream

SPECIAL CASE - COMBINED COLUMNS:
If a vendor column contains COMBINED data that matches MULTIPLE standard columns, detect this pattern.
Example: vendor column "customer_detail" with values like "(Big Bazaar, CUST_001)" should map to BOTH "customer_name" AND "customer_code".
When you detect combined data, use the "splits" section to specify how to split it.

Format patterns to detect:
- "(value1,value2)" - comma-separated values in parentheses
- "value1,value2" - comma-separated values
- "value1|value2" - pipe-separated values
- Any pattern where one column contains multiple pieces of information

Return STRICT JSON ONLY:
{{
  "mapping": {{
    "vendor_column": "standard_column"
  }},
  "splits": {{
    "vendor_column": {{
      "format": "description of format like '(value1,value2)'",
      "targets": ["standard_column1", "standard_column2"]
    }}
  }}
}}

Example for combined column:
{{
  "mapping": {{
    "customer_detail": "customer_name"
  }},
  "splits": {{
    "customer_detail": {{
      "format": "(customer_name,customer_code)",
      "targets": ["customer_name", "customer_code"]
    }}
  }}
}}

Note: "splits" is optional - only include if you detect combined columns.
"""

    response = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    data = extract_json(response.choices[0].message.content)

    if "mapping" not in data or not isinstance(data["mapping"], dict):
        raise ValueError("AI mapping response missing valid 'mapping' object")

    # Return both mapping and splits (splits may be empty)
    result = {
        "mapping": data["mapping"],
        "splits": data.get("splits", {})
    }
    
    return result
