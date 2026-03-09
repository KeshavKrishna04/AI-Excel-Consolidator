from llm.openrouter_client import get_llm
from llm.json_utils import extract_json
import json

def validate_sheet(profile, mapping, domain):
    """
    AI-based semantic validation.
    Determines whether the sheet is usable for consolidation
    even if incomplete.
    
    Note: mapping can be either:
    - dict: {vendor_col: standard_col} (old format)
    - dict: {"mapping": {...}, "splits": {...}} (new format)
    """
    client = get_llm()
    
    # Handle new format with splits for validation
    if isinstance(mapping, dict) and "mapping" in mapping:
        mapping_to_validate = mapping["mapping"]
    else:
        mapping_to_validate = mapping

    prompt = f"""
You are validating whether a sheet is usable {domain.upper()} data.

Vendor column profile:
{json.dumps(profile, indent=2)}

Proposed schema mapping:
{json.dumps(mapping_to_validate, indent=2)}

Rules:
- Missing columns are allowed
- Do NOT expect a perfect schema
- Accept if the sheet clearly represents {domain} data
- Reject ONLY if the sheet is semantically unrelated or unusable

Return STRICT JSON ONLY:
{{
  "accept": true | false,
  "reason": "short explanation"
}}
"""

    response = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    data = extract_json(response.choices[0].message.content)

    if "accept" not in data:
        raise ValueError("AI validation response missing 'accept' field")

    return data
