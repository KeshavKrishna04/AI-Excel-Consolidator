import json
import pandas as pd
from llm.openrouter_client import get_llm
from llm.json_utils import extract_json


def enrich_state_from_city(df, city_column="city", state_column="state"):
    """
    Uses AI to fill missing state values based on city names.
    
    Args:
        df: pandas DataFrame with city and state columns
        city_column: Name of city column
        state_column: Name of state column to fill
    
    Returns:
        DataFrame with state column enriched
    """
    if city_column not in df.columns or state_column not in df.columns:
        return df
    
    # Get unique city-state pairs where state is missing
    df = df.copy()
    
    # Find rows with city but no state
    missing_state_mask = df[state_column].isna() & df[city_column].notna()
    
    if not missing_state_mask.any():
        return df  # Nothing to fill
    
    # Get unique cities that need state
    cities_to_fill = df.loc[missing_state_mask, city_column].unique()
    
    if len(cities_to_fill) == 0:
        return df
    
    client = get_llm()
    
    prompt = f"""
You are a geographic data enrichment AI for Indian cities and states.

Given a list of city names, determine the corresponding Indian state for each city.
If a city name is not a real Indian city (e.g., "Online", "Digital", "E-commerce"), return "Unknown" or leave it empty.

City names to map:
{json.dumps(list(cities_to_fill), indent=2)}

Rules:
- Return the correct Indian state name for each city
- Use standard state names (e.g., "Maharashtra", "Tamil Nadu", "Karnataka")
- If city is ambiguous (e.g., multiple states have cities with same name), choose the most common/prominent one
- If city is not a real location or is online/virtual, return "Unknown"
- Be accurate with spelling and capitalization

Return STRICT JSON ONLY:
{{
  "mapping": {{
    "city_name": "State Name"
  }}
}}

Example:
{{
  "mapping": {{
    "Mumbai": "Maharashtra",
    "Chennai": "Tamil Nadu",
    "Bangalore": "Karnataka",
    "Delhi": "Delhi",
    "Online": "Unknown"
  }}
}}
"""
    
    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        
        data = extract_json(response.choices[0].message.content)
        
        if "mapping" not in data or not isinstance(data["mapping"], dict):
            print("    Warning: Invalid response from state enrichment AI")
            return df
        
        city_to_state = data["mapping"]
        
        # Fill missing states
        def get_state(row):
            if pd.isna(row[state_column]) and pd.notna(row[city_column]):
                city = str(row[city_column]).strip()
                # Try exact match first
                if city in city_to_state:
                    state = city_to_state[city]
                    return state if state != "Unknown" and state != "" else None
                # Try case-insensitive match
                city_lower = city.lower()
                for city_key, state_value in city_to_state.items():
                    if city_key.lower() == city_lower:
                        state = state_value
                        return state if state != "Unknown" and state != "" else None
            return row[state_column]
        
        # Apply enrichment
        df[state_column] = df.apply(get_state, axis=1)
        
        filled_count = df.loc[missing_state_mask, state_column].notna().sum()
        print(f"    Enriched {filled_count} state values from city names")
        
    except Exception as e:
        print(f"    Warning: State enrichment failed: {e}")
    
    return df
