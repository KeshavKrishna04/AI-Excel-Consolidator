import json

from llm.openrouter_client import get_llm
from llm.json_utils import extract_json


def detect_domain(sheet_name: str, column_names: list, profile: dict) -> dict:
    """
    Uses AI to determine whether a sheet belongs to:
    - sales
    - nielsen
    - pricing
    - competitor
    - baseline

    Uses sheet name, column names, and sample values.
    """

    client = get_llm()

    prompt = f"""
You are a domain classification AI for enterprise data pipelines.

Possible domains (STRICT):
- sales: Transaction-level data with transaction_id, customer details, sales quantities, revenue, discounts, COGS, margins. Focus: individual transactions, customers, products sold.
- nielsen: Market research/retail measurement data with week_ending/reporting_week, market share, brand sales, distribution metrics, competitor shares. Focus: market analytics, brand performance, competitive intelligence.
- pricing: Pricing data with price points, promotional pricing, pricing tiers, product pricing. Focus: price management, pricing strategies.
- competitor: Competitor analysis data with brand_name, brand_category, market_share_percent, price_index, brand_strength, primary_channels, key_regions. Focus: competitor intelligence, brand positioning, market analysis.
- baseline: Baseline/metric data with period, metric_name, metric_value, unit. Focus: baseline metrics, KPIs, performance indicators, time-series metrics (e.g., total_nsv, sales_volume, market_size).

Sheet name:
{sheet_name}

Column names:
{column_names}

Semantic column profile (includes sample values):
{json.dumps(profile, indent=2)}

Rules:
- Choose ONLY one domain based on COLUMN NAMES and DATA MEANING, not just sheet name
- Nielsen data typically has: market_share, brand_sales, category_sales, distribution metrics, competitor shares
- Sales data typically has: transaction_id, customer_code, sales_qty, revenue, discounts, COGS
- Competitor data typically has: brand_name, brand_category, market_share_percent/avg_market_share_percent, price_index/avg_price_index, brand_strength, primary_channels, key_regions
- Pricing data typically has: price points, promotional pricing, pricing tiers
- Baseline data typically has: period/date, metric_name (e.g., total_nsv, sales_volume), metric_value, unit (e.g., INR, cases)
- Do NOT be misled by sheet names (e.g., "Weekly_Sales" might still be nielsen data if columns indicate market research)
- Base decision on COLUMN SEMANTICS and VALUES, not naming alone
- Be conservative - return "unknown" if unclear

Return STRICT JSON ONLY:
{{
  "domain": "sales | nielsen | pricing | competitor | baseline | unknown",
  "confidence": 0.0-1.0,
  "reason": "short explanation"
}}
"""

    response = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    data = extract_json(response.choices[0].message.content)

    if "domain" not in data:
        raise ValueError("AI domain response missing 'domain' field")

    return data
