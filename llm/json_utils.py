import json
import re

def extract_json(text: str) -> dict:
    """
    Safely extract JSON from LLM output.
    Handles:
    - ```json fences
    - extra explanatory text
    - whitespace
    """
    if not text or not text.strip():
        raise ValueError("Empty response from LLM")

    # Remove markdown code fences
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()

    # Extract first JSON object found
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response:\n{cleaned}")

    try:
        return json.loads(match.group())
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Invalid JSON extracted from LLM response:\n{match.group()}"
        ) from e
