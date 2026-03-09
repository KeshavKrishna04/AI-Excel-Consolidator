# AI Consolidator Excel - Complete Project Explanation

## 📋 Table of Contents
1. [Project Overview](#project-overview)
2. [Architecture & Structure](#architecture--structure)
3. [Dependencies & Libraries](#dependencies--libraries)
4. [Control Flow](#control-flow)
5. [Data Flow](#data-flow)
6. [File-by-File Detailed Explanation](#file-by-file-detailed-explanation)
7. [How Everything Works Together](#how-everything-works-together)

---

## 🎯 Project Overview

**Purpose**: This is an AI-powered Excel data consolidation system that:
- Takes vendor Excel files with different schema variations
- Uses AI to detect the domain (sales/nielsen/pricing)
- Maps vendor columns to standard schema columns semantically
- Consolidates multiple vendor files into standardized output files

**Core Problem Solved**: Different vendors provide data in different formats. This system automatically:
1. Identifies what type of data it is (domain detection)
2. Maps columns intelligently (semantic mapping)
3. Transforms data to match standard schemas
4. Consolidates all data into clean, standardized Excel files

---

## 🏗️ Architecture & Structure

```
AI Consolidator Excel/
│
├── main.py                 # Entry point, orchestrates entire pipeline
├── requirements.txt        # Python dependencies
│
├── core/                   # Core data processing modules
│   ├── excel_loader.py     # Loads Excel files into DataFrames
│   ├── standard_parser.py  # Extracts standard schemas from reference files
│   ├── consolidator.py     # Maps and consolidates data
│   └── excel_writer.py     # Writes DataFrames to Excel
│
├── agents/                 # AI-powered agents for intelligent processing
│   ├── schema_agent.py     # Profiles data sheets (analyzes columns + values)
│   ├── domain_agent.py     # Detects domain (sales/nielsen/pricing)
│   ├── mapping_agent.py    # Maps vendor columns → standard columns
│   └── validation_agent.py # Validates if sheet is usable
│
├── llm/                    # LLM integration utilities
│   ├── openrouter_client.py # OpenAI/OpenRouter API client
│   └── json_utils.py       # Extracts JSON from LLM responses
│
├── config/                 # Configuration files
│   └── domains.py          # Domain definitions
│
├── data/                   # Input data directory
│   ├── sales.xlsx          # Standard sales schema (reference)
│   ├── nielsen.xlsx        # Standard nielsen schema (reference)
│   ├── pricing.xlsx        # Standard pricing schema (reference)
│   ├── sales_schema_1.xlsx # Vendor sales file (input)
│   └── nielsen_schema_1.xlsx # Vendor nielsen file (input)
│
└── outputs/                # Output directory
    ├── consolidated_sales.xlsx
    ├── consolidated_nielsen.xlsx
    └── consolidated_pricing.xlsx
```

---

## 📦 Dependencies & Libraries

### requirements.txt Breakdown:

#### 1. **pandas>=2.1.0**
- **Purpose**: Core data manipulation library
- **Used For**:
  - Reading Excel files (`pd.read_excel()`, `pd.ExcelFile()`)
  - Data manipulation (DataFrames, Series)
  - Data transformation and concatenation
  - Writing Excel files (`df.to_excel()`)
- **Why**: Essential for all Excel I/O and data processing

#### 2. **openpyxl>=3.1.2**
- **Purpose**: Excel file format support for pandas
- **Used For**:
  - Reading/writing .xlsx files
  - Specified as engine in `df.to_excel(engine='openpyxl')`
- **Why**: pandas needs this to handle Excel files (especially newer formats)

#### 3. **python-dotenv>=1.0.0**
- **Purpose**: Loads environment variables from .env file
- **Used For**:
  - Loading API keys securely
  - Configuration management
- **Why**: Keeps API keys out of code (security best practice)

#### 4. **requests>=2.31.0**
- **Purpose**: HTTP library (indirect dependency)
- **Used For**: 
  - API calls to LLM services
  - Handled by OpenAI SDK internally
- **Why**: Required by OpenAI SDK

#### 5. **openai>=1.0.0**
- **Purpose**: OpenAI/OpenRouter API client SDK
- **Used For**:
  - Creating LLM client connections
  - Sending prompts to AI models
  - Receiving AI responses
- **Why**: Enables AI-powered features (domain detection, mapping, validation)

---

## 🔄 Control Flow

### High-Level Pipeline Flow:

```
START (main.py __main__)
│
├─ 1. DISCOVER VENDOR FILES
│   └─> Scans data/ directory
│   └─> Filters out standard files
│   └─> Gets list of vendor files to process
│
├─ 2. LOAD STANDARD SCHEMAS
│   └─> main.load_all_standard_schemas()
│       └─> For each domain (sales/nielsen/pricing):
│           └─> core.standard_parser.extract_standard_schemas()
│               └─> Reads standard Excel file
│               └─> Extracts column names (ordered)
│       └─> Returns: {domain: [column_names]}
│
├─ 3. PROCESS EACH VENDOR FILE
│   │
│   └─> FOR EACH vendor_file:
│       │
│       ├─ 3.1 LOAD SHEETS
│       │   └─> core.excel_loader.load_excel_sheets()
│       │       └─> Reads all sheets from Excel
│       │       └─> Returns: [(sheet_name, DataFrame), ...]
│       │
│       └─> FOR EACH sheet:
│           │
│           ├─ 3.2 PROFILE SHEET
│           │   └─> agents.schema_agent.profile_sheet()
│           │       └─> Analyzes columns
│           │       └─> Extracts data types
│           │       └─> Gets sample values (first 5)
│           │       └─> Returns: {col: {dtype, samples}}
│           │
│           ├─ 3.3 DETECT DOMAIN
│           │   └─> agents.domain_agent.detect_domain()
│           │       └─> Calls LLM with sheet name, columns, profile
│           │       └─> LLM analyzes semantic meaning
│           │       └─> Returns: {domain, confidence, reason}
│           │
│           ├─ 3.4 CHECK DOMAIN SUPPORT
│           │   └─> If domain not in ["sales", "nielsen", "pricing"]:
│           │       └─> Skip sheet
│           │
│           ├─ 3.5 GENERATE MAPPING
│           │   └─> agents.mapping_agent.generate_schema_mapping()
│           │       └─> Calls LLM with profile + standard columns
│           │       └─> LLM maps vendor columns → standard columns
│           │       └─> Returns: {vendor_col: standard_col}
│           │
│           ├─ 3.6 VALIDATE SHEET
│           │   └─> agents.validation_agent.validate_sheet()
│           │       └─> Calls LLM with profile + mapping
│           │       └─> LLM decides if sheet is usable
│           │       └─> Returns: {accept: bool, reason}
│           │
│           ├─ 3.7 CONSOLIDATE DATA
│           │   └─> core.consolidator.consolidate_domain_data()
│           │       └─> Inverts mapping: {standard: vendor}
│           │       └─> For each row in vendor data:
│           │           └─> Maps values to standard columns
│           │           └─> Adds source_file, source_sheet
│           │       └─> Concatenates with existing consolidated data
│           │       └─> Returns: Consolidated DataFrame
│           │
│           └─> Update consolidated[domain]
│
├─ 4. WRITE OUTPUT FILES
│   └─> FOR EACH domain with data:
│       └─> core.excel_writer.write_excel()
│           └─> Writes DataFrame to Excel
│           └─> Creates outputs/consolidated_{domain}.xlsx
│
END
```

---

## 📊 Data Flow

### Data Transformation Pipeline:

```
INPUT FILES (Vendor Schemas)
│
├─ sales_schema_1.xlsx
│   └─ Columns: ['transaction_id', 'material_description', 'brand_name', ...]
│   └─ Rows: 50 rows of vendor-formatted data
│
└─ nielsen_schema_1.xlsx
    └─ Columns: ['reporting_week', 'category', 'brand_name', 'market_share_pct', ...]
    └─ Rows: 50 rows of vendor-formatted data
│
┐
│ [1] EXCEL LOADER
│     ↓
├─ DataFrame objects (pandas)
│   └─ sales_schema_1: DataFrame with vendor columns
│   └─ nielsen_schema_1: DataFrame with vendor columns
│
│ [2] SCHEMA AGENT (Profile)
│     ↓
├─ Profile dictionaries
│   └─ sales_schema_1: {col: {dtype: "object", samples: [...]}}
│   └─ nielsen_schema_1: {col: {dtype: "object", samples: [...]}}
│
│ [3] DOMAIN AGENT (LLM)
│     ↓
├─ Domain classification
│   └─ sales_schema_1 → "sales"
│   └─ nielsen_schema_1 → "nielsen"
│
│ [4] MAPPING AGENT (LLM)
│     ↓
├─ Column mappings
│   └─ sales_schema_1: {
│         "brand_name": "brand",
│         "material_description": "material_name",
│         ...
│       }
│   └─ nielsen_schema_1: {
│         "reporting_week": "week_ending",
│         "brand_name": "brand",
│         "market_share_pct": "market_share_percent",
│         ...
│       }
│
│ [5] CONSOLIDATOR
│     ↓
├─ Standardized DataFrames
│   └─ Consolidated Sales:
│       └─ Columns: [standard sales columns + source_file + source_sheet]
│       └─ Rows: Mapped and transformed data
│   └─ Consolidated Nielsen:
│       └─ Columns: [standard nielsen columns + source_file + source_sheet]
│       └─ Rows: Mapped and transformed data
│
│ [6] EXCEL WRITER
│     ↓
└─ OUTPUT FILES (Standard Schemas)
    │
    ├─ consolidated_sales.xlsx
    │   └─ Columns: ['transaction_id', 'transaction_date', 'material_code', ...]
    │   └─ Rows: All consolidated sales data
    │
    └─ consolidated_nielsen.xlsx
        └─ Columns: ['week_ending', 'category', 'brand', 'market_share_percent', ...]
        └─ Rows: All consolidated nielsen data
```

### Data Mapping Example:

**Input (Vendor Schema)**:
```
brand_name      material_description    sales_channel
"FRESHFLOW"     "FreshFlow Mango 1L"    "MT"
```

**Mapping**:
```python
{
    "brand_name": "brand",
    "material_description": "material_name",
    "sales_channel": "channel"
}
```

**Output (Standard Schema)**:
```
brand           material_name           channel
"FRESHFLOW"     "FreshFlow Mango 1L"    "MT"
```

---

## 📁 File-by-File Detailed Explanation

### 1. **main.py** - Orchestration & Entry Point

**Purpose**: Main entry point that orchestrates the entire consolidation pipeline.

**Imports & Their Roles**:
```python
import os                    # File system operations (path handling, directory creation)
import pandas as pd          # DataFrame operations (type checking, data structures)

# Core modules
from core.excel_loader import load_excel_sheets
from core.standard_parser import extract_standard_schemas
from core.consolidator import consolidate_domain_data
from core.excel_writer import write_excel

# AI agents
from agents.domain_agent import detect_domain
from agents.schema_agent import profile_sheet
from agents.mapping_agent import generate_schema_mapping
from agents.validation_agent import validate_sheet
```

**Key Constants**:
- `DATA_DIR = "data"`: Input directory path
- `OUTPUT_DIR = "outputs"`: Output directory path
- `STANDARD_FILES`: Dictionary mapping domains to their standard schema files

**Functions**:

#### `load_all_standard_schemas()`
- **Input**: None (reads from STANDARD_FILES)
- **Process**:
  1. Iterates through each domain (sales, nielsen, pricing)
  2. Checks if standard file exists
  3. Calls `extract_standard_schemas()` to get column names
  4. Handles sheet name matching (domain might not match sheet name like "Sheet1")
  5. Returns first schema found if domain doesn't match sheet name
- **Output**: `{domain: [ordered_column_names]}`
- **Example Output**:
  ```python
  {
      "sales": ["transaction_id", "transaction_date", "material_code", ...],
      "nielsen": ["week_ending", "category", "brand", ...],
      "pricing": [...]
  }
  ```

#### `run_pipeline(vendor_files)`
- **Input**: List of file paths to vendor Excel files
- **Process**: 7-step pipeline
  1. **Load Standards**: Gets standard schemas for all domains
  2. **Initialize**: Creates empty consolidated dictionaries for each domain
  3. **Process Files**: For each vendor file:
     - Loads all sheets
     - For each sheet:
       - Profiles data (gets column info + samples)
       - Detects domain using AI
       - Generates column mapping using AI
       - Validates mapping using AI
       - Consolidates data (transforms and merges)
  4. **Write Outputs**: Writes consolidated DataFrames to Excel files
- **Output**: Excel files in outputs/ directory

#### `__main__` Block
- **Process**:
  1. Normalizes paths (handles Windows/Unix differences)
  2. Scans `data/` directory for .xlsx files
  3. Filters out standard files (to avoid processing reference files)
  4. Calls `run_pipeline()` with vendor files
- **Error Handling**: Checks if vendor files exist

---

### 2. **core/excel_loader.py** - Excel File Reader

**Purpose**: Loads Excel files and converts them to pandas DataFrames.

**Imports**:
```python
import pandas as pd  # Excel reading: pd.read_excel()
```

**Function**:

#### `load_excel_sheets(path: str)`
- **Input**: File path string (e.g., "data/sales_schema_1.xlsx")
- **Process**:
  1. Uses `pd.read_excel(path, sheet_name=None)` to read ALL sheets
  2. Returns dictionary: `{sheet_name: DataFrame}`
  3. Filters out non-DataFrame objects (safety check)
  4. Skips empty sheets
  5. Normalizes column names (trims whitespace)
  6. Converts to list of tuples: `[(sheet_name, DataFrame), ...]`
- **Output**: List of tuples: `[("Sheet1", DataFrame), ("Sheet2", DataFrame), ...]`
- **Error Handling**: Raises ValueError if file can't be read or no usable sheets found

**Why `sheet_name=None`?**
- Reads all sheets at once instead of one-by-one
- More efficient for multi-sheet files

**Example**:
```python
Input: "data/sales.xlsx" (has 1 sheet "Sales_Data")
Output: [("Sales_Data", DataFrame with 50 rows, 23 columns)]
```

---

### 3. **core/standard_parser.py** - Schema Extractor

**Purpose**: Extracts column names (schema) from standard reference files.

**Imports**:
```python
import pandas as pd  # ExcelFile for sheet inspection, parse() for reading
```

**Function**:

#### `extract_standard_schemas(path: str) -> dict`
- **Input**: Path to standard Excel file
- **Process**:
  1. Opens Excel file with `pd.ExcelFile(path)` (lighter than full read)
  2. Gets all sheet names
  3. For each sheet:
     - Parses sheet into DataFrame
     - Skips empty sheets
     - Extracts column names, trims whitespace
     - Stores as: `{sheet_name.lower(): [columns]}`
  4. Returns dictionary of schemas
- **Output**: `{sheet_name: [column_names], ...}`
- **Why lowercase sheet names?**: Normalizes matching (handles "Sheet1" vs "sheet1")

**Example**:
```python
Input: "data/sales.xlsx" (Sheet1 has columns: ['transaction_id', 'transaction_date', ...])
Output: {"sheet1": ["transaction_id", "transaction_date", ...]}
```

**Key Feature**: Only extracts column names, not data. This is the "schema template" used for mapping.

---

### 4. **core/consolidator.py** - Data Transformer & Merger

**Purpose**: Transforms vendor data to match standard schema and consolidates multiple sources.

**Imports**:
```python
import pandas as pd  # DataFrame operations, row iteration, concatenation
```

**Function**:

#### `consolidate_domain_data(existing_df, new_df, mapping, standard_columns, source_file, source_sheet)`
- **Inputs**:
  - `existing_df`: Previously consolidated DataFrame (None if first file)
  - `new_df`: New vendor DataFrame to add
  - `mapping`: `{vendor_column: standard_column}` dictionary
  - `standard_columns`: List of standard column names (target schema)
  - `source_file`: Name of source file (for lineage tracking)
  - `source_sheet`: Name of source sheet (for lineage tracking)

- **Process**:
  1. **Column Setup**: Creates list of all output columns (standard + lineage)
  2. **Mapping Inversion**: Converts `{vendor: standard}` → `{standard: vendor}`
     - **Why?**: Need to look up "which vendor column maps to standard column X"
     - Example: `{"brand_name": "brand"}` → `{"brand": "brand_name"}`
  3. **Initialize Output**: Creates empty DataFrame with standard columns if first file
  4. **Row-by-Row Transformation**:
     - For each row in vendor data:
       - Creates empty output row
       - For each standard column:
         - Looks up mapped vendor column
         - Copies value if mapping exists
         - Sets to None if no mapping
       - Adds source_file and source_sheet
  5. **Concatenation**: Combines new rows with existing consolidated data
- **Output**: Consolidated DataFrame with standard schema + source tracking

**Critical Logic - Mapping Inversion**:
```python
# Input mapping from AI agent:
{"brand_name": "brand", "material_description": "material_name"}

# Inverted for lookups:
{"brand": "brand_name", "material_name": "material_description"}

# Then for each standard column "brand":
vendor_col = inverted_mapping.get("brand")  # Returns "brand_name"
value = row["brand_name"]  # Gets value from vendor data
out_row["brand"] = value   # Sets in standard format
```

**Example Transformation**:
```python
Input DataFrame (vendor):
  brand_name    material_description
  "FRESHFLOW"   "FreshFlow Mango 1L"

Mapping: {"brand_name": "brand", "material_description": "material_name"}

Output DataFrame (standard):
  brand         material_name          source_file          source_sheet
  "FRESHFLOW"   "FreshFlow Mango 1L"   "sales_schema_1.xlsx" "Sales_Data"
```

---

### 5. **core/excel_writer.py** - Excel File Writer

**Purpose**: Writes DataFrames to Excel files with error handling.

**Imports**:
```python
import os          # Path operations, file existence checks, directory creation
import pandas as pd # DataFrame.to_excel() method
```

**Function**:

#### `write_excel(df, path)`
- **Input**:
  - `df`: pandas DataFrame to write
  - `path`: Output file path
- **Process**:
  1. Creates output directory if it doesn't exist (`os.makedirs()`)
  2. Checks if file exists
  3. Tries to remove existing file (to overwrite)
  4. Handles PermissionError (file locked in Excel)
  5. Writes DataFrame using `df.to_excel(path, index=False, engine='openpyxl')`
- **Why `index=False`?**: Don't write row numbers (cleaner Excel output)
- **Why `engine='openpyxl'`?**: Explicitly use openpyxl for .xlsx format

**Error Handling**: Raises PermissionError with helpful message if file is locked.

---

### 6. **agents/schema_agent.py** - Data Profiler

**Purpose**: Creates semantic profiles of Excel sheets by analyzing columns and sample values.

**Imports**:
```python
import pandas as pd  # DataFrame operations, Series manipulation, type detection
```

**Function**:

#### `profile_sheet(df: pd.DataFrame, sample_size: int = 5) -> dict`
- **Input**:
  - `df`: DataFrame to profile
  - `sample_size`: Number of sample values to extract (default: 5)
- **Process**:
  1. For each column in DataFrame:
     - Drops NaN values to get valid data
     - Extracts data type (string representation)
     - Gets first N sample values (converted to string for AI readability)
  2. Returns profile dictionary
- **Output**: `{column_name: {dtype: "...", samples: [...]}}`

**Why Profile?**: AI agents need to understand:
- **Column names**: "brand_name" vs "brand"
- **Data types**: String vs numeric vs date
- **Sample values**: "FRESHFLOW" (uppercase) vs "FreshFlow" (mixed case)
- This helps AI make semantic matches, not just name-based

**Example Output**:
```python
{
    "brand_name": {
        "dtype": "object",
        "samples": ["FRESHFLOW", "COLA", "JUICE"]
    },
    "sales_qty": {
        "dtype": "int64",
        "samples": ["50", "100", "75"]
    }
}
```

---

### 7. **agents/domain_agent.py** - Domain Classifier (AI)

**Purpose**: Uses AI to detect which domain a sheet belongs to (sales/nielsen/pricing).

**Imports**:
```python
import json                    # JSON serialization for prompt
from llm.openrouter_client import get_llm  # LLM client
from llm.json_utils import extract_json    # JSON extraction from LLM response
```

**Function**:

#### `detect_domain(sheet_name: str, column_names: list, profile: dict) -> dict`
- **Input**:
  - `sheet_name`: Name of Excel sheet
  - `column_names`: List of column names
  - `profile`: Semantic profile from schema_agent
- **Process**:
  1. Gets LLM client (`get_llm()`)
  2. Constructs prompt with:
     - Domain definitions (sales/nielsen/pricing characteristics)
     - Sheet name
     - Column names
     - Full semantic profile (column names + data types + sample values)
     - Rules for classification
  3. Sends prompt to LLM (`client.chat.completions.create()`)
  4. Extracts JSON from LLM response
  5. Validates response has "domain" field
- **Output**: `{domain: "sales|nielsen|pricing|unknown", confidence: 0.0-1.0, reason: "..."}`

**LLM Configuration**:
- Model: `"openai/gpt-4o-mini"` (fast, cost-effective)
- Temperature: `0` (deterministic, consistent results)

**Prompt Strategy**:
- Emphasizes column semantics over sheet names
- Includes sample values for context
- Asks for conservative classification (return "unknown" if unclear)

**Example**:
```python
Input: 
  sheet_name: "Weekly_Sales"
  columns: ["reporting_week", "brand_sales", "market_share_pct"]
  
Output: 
  {"domain": "nielsen", "confidence": 0.95, "reason": "Has market share and reporting week"}
```

---

### 8. **agents/mapping_agent.py** - Column Mapper (AI)

**Purpose**: Uses AI to map vendor columns to standard columns semantically.

**Imports**:
```python
import json                    # JSON serialization
from llm.openrouter_client import get_llm  # LLM client
from llm.json_utils import extract_json    # JSON extraction
```

**Function**:

#### `generate_schema_mapping(profile: dict, standard_columns: list) -> dict`
- **Input**:
  - `profile`: Vendor column profile (from schema_agent)
  - `standard_columns`: List of standard column names (target schema)
- **Process**:
  1. Gets LLM client
  2. Constructs prompt with:
     - Vendor profile (columns + types + samples)
     - Standard columns (authoritative target schema)
     - Instructions for semantic mapping
  3. Sends to LLM
  4. Extracts JSON mapping from response
  5. Validates mapping structure
- **Output**: `{vendor_column: standard_column}`

**Prompt Strategy**:
- Emphasizes semantic meaning, not just name matching
- Uses sample values to disambiguate (e.g., "ID" vs "Code" vs "Name")
- Conservative: omits uncertain mappings
- Partial mappings allowed (not all columns need to map)

**Example**:
```python
Input:
  profile: {"brand_name": {dtype: "object", samples: ["FRESHFLOW"]}, ...}
  standard_columns: ["brand", "category", "sub_category", ...]

Output:
  {
      "brand_name": "brand",
      "category": "category",
      "subcategory": "sub_category",
      ...
  }
```

**Key Insight**: AI uses both column names AND sample values to understand meaning:
- "brand_name" + samples like ["FRESHFLOW"] → maps to "brand"
- "material_description" + samples like ["FreshFlow Mango 1L"] → maps to "material_name"

---

### 9. **agents/validation_agent.py** - Quality Validator (AI)

**Purpose**: Uses AI to validate if a sheet is usable for consolidation.

**Imports**:
```python
from llm.openrouter_client import get_llm  # LLM client
from llm.json_utils import extract_json    # JSON extraction
import json                                # JSON serialization
```

**Function**:

#### `validate_sheet(profile, mapping, domain) -> dict`
- **Input**:
  - `profile`: Vendor column profile
  - `mapping`: Generated column mapping
  - `domain`: Detected domain
- **Process**:
  1. Gets LLM client
  2. Constructs validation prompt:
     - Vendor profile
     - Proposed mapping
     - Validation rules (missing columns OK, just check if related)
  3. Sends to LLM
  4. Extracts JSON response
- **Output**: `{accept: bool, reason: "..."}`

**Purpose**: Quality gate to filter out:
- Completely unrelated data (wrong domain entirely)
- Malformed data that can't be used
- But allows incomplete data (missing some columns is OK)

**Example**:
```python
Input: 
  domain: "sales"
  mapping: {"brand_name": "brand", "category": "category"}
  
Output: 
  {"accept": true, "reason": "Sufficient sales-related columns mapped"}
```

---

### 10. **llm/openrouter_client.py** - LLM Client Factory

**Purpose**: Creates OpenAI-compatible client for LLM API calls.

**Imports**:
```python
import os                    # Environment variable access
from dotenv import load_dotenv  # Loads .env file
from openai import OpenAI     # OpenAI SDK client
```

**Function**:

#### `get_llm()`
- **Process**:
  1. Loads `.env` file (reads environment variables)
  2. Gets `OPENAI_API_BASE` from environment (API endpoint URL)
  3. Gets `OPENAI_API_KEY` from environment (authentication key)
  4. Creates and returns OpenAI client
- **Output**: OpenAI client instance

**Configuration**:
- Uses `.env` file for credentials (security)
- Supports OpenRouter (compatible API) or OpenAI directly
- Base URL and API key are configurable

**Why OpenRouter?**:
- Unified API for multiple LLM providers
- Cost-effective routing
- Same interface as OpenAI

**Required .env file**:
```
OPENAI_API_BASE=https://openrouter.ai/api/v1
OPENAI_API_KEY=sk-or-v1-...
```

---

### 11. **llm/json_utils.py** - JSON Extractor

**Purpose**: Safely extracts JSON from LLM responses (which may have extra text).

**Imports**:
```python
import json  # JSON parsing
import re    # Regular expressions for text cleaning
```

**Function**:

#### `extract_json(text: str) -> dict`
- **Input**: Raw LLM response text (may include markdown, explanations, etc.)
- **Process**:
  1. Checks if text is empty
  2. Removes markdown code fences (```json ... ```)
  3. Strips whitespace
  4. Uses regex to find first JSON object `{.*}` (with DOTALL flag for multiline)
  5. Parses JSON
  6. Returns parsed dictionary
- **Output**: Parsed JSON dictionary
- **Error Handling**: Raises ValueError with helpful messages if JSON not found or invalid

**Why Needed?**: LLMs sometimes return:
```
Here's the mapping:
```json
{"mapping": {"brand_name": "brand"}}
```
Let me know if you need anything else!
```

This function extracts just the JSON part.

**Example**:
```python
Input: "```json\n{\"mapping\": {\"brand_name\": \"brand\"}}\n```"
Output: {"mapping": {"brand_name": "brand"}}
```

---

### 12. **config/domains.py** - Domain Configuration

**Purpose**: Simple configuration file listing supported domains.

**Content**:
```python
DOMAINS = ["nielsen", "sales", "pricing"]
```

**Note**: Currently minimal, but could be expanded for domain-specific rules, validation criteria, etc.

---

## 🔗 How Everything Works Together

### Complete Execution Flow Example:

#### Scenario: Processing `sales_schema_1.xlsx` and `nielsen_schema_1.xlsx`

**Step 1: Initialization** (`main.py` __main__)
```
1. Scans data/ directory
2. Finds: sales_schema_1.xlsx, nielsen_schema_1.xlsx (vendor files)
3. Excludes: sales.xlsx, nielsen.xlsx, pricing.xlsx (standard files)
4. Calls run_pipeline(["data/sales_schema_1.xlsx", "data/nielsen_schema_1.xlsx"])
```

**Step 2: Load Standards** (`main.py` → `core/standard_parser.py`)
```
1. Reads data/sales.xlsx → extracts columns: ["transaction_id", "transaction_date", ...]
2. Reads data/nielsen.xlsx → extracts columns: ["week_ending", "category", ...]
3. Reads data/pricing.xlsx → extracts columns: [...]
4. Returns schemas dictionary for all domains
```

**Step 3: Process sales_schema_1.xlsx**

**3a. Load** (`core/excel_loader.py`)
```
→ Reads Excel → Returns: [("Sales_Data", DataFrame)]
```

**3b. Profile** (`agents/schema_agent.py`)
```
→ Analyzes DataFrame → Returns: {
    "transaction_id": {dtype: "object", samples: ["TXN_1", "TXN_2"]},
    "brand_name": {dtype: "object", samples: ["FRESHFLOW"]},
    ...
}
```

**3c. Detect Domain** (`agents/domain_agent.py`)
```
→ Sends prompt to LLM with profile
→ LLM analyzes: "transaction_id", "customer_code", "sales_qty" → sales domain
→ Returns: {domain: "sales", confidence: 0.95}
```

**3d. Map Columns** (`agents/mapping_agent.py`)
```
→ Sends prompt to LLM with vendor profile + standard sales columns
→ LLM maps:
    "brand_name" → "brand"
    "material_description" → "material_name"
    "sales_channel" → "channel"
→ Returns: {vendor_col: standard_col}
```

**3e. Validate** (`agents/validation_agent.py`)
```
→ Sends prompt to LLM with profile + mapping
→ LLM confirms: "Sufficient sales columns mapped"
→ Returns: {accept: true}
```

**3f. Consolidate** (`core/consolidator.py`)
```
→ Inverts mapping: {standard: vendor}
→ For each row in vendor data:
    - Maps "brand_name" value → "brand" column
    - Maps "material_description" → "material_name" column
    - Sets unmapped columns to None
    - Adds source_file="sales_schema_1.xlsx"
→ Concatenates to consolidated["sales"]
```

**Step 4: Process nielsen_schema_1.xlsx** (same steps as Step 3, but domain="nielsen")

**Step 5: Write Outputs** (`core/excel_writer.py`)
```
→ consolidated["sales"] → outputs/consolidated_sales.xlsx
→ consolidated["nielsen"] → outputs/consolidated_nielsen.xlsx
→ consolidated["pricing"] → skipped (no data)
```

### Data Transformation Example:

**Vendor Input (sales_schema_1.xlsx)**:
| transaction_id | brand_name | material_description | sales_channel |
|----------------|------------|----------------------|---------------|
| TXN_1          | FRESHFLOW  | FreshFlow Mango 1L   | MT            |

**Standard Schema (from sales.xlsx)**:
```
["transaction_id", "brand", "material_name", "channel", ...]
```

**AI Mapping Generated**:
```python
{
    "transaction_id": "transaction_id",  # Direct match
    "brand_name": "brand",                # Name variation
    "material_description": "material_name",  # Synonym
    "sales_channel": "channel"            # Abbreviation
}
```

**Consolidated Output**:
| transaction_id | brand      | material_name      | channel | source_file          | source_sheet |
|----------------|------------|--------------------|---------|----------------------|--------------|
| TXN_1          | FRESHFLOW  | FreshFlow Mango 1L | MT      | sales_schema_1.xlsx  | Sales_Data   |

---

## 🎯 Key Design Decisions

### 1. **Why AI Agents?**
- **Semantic Understanding**: Handles column name variations (brand_name vs brand)
- **Context-Aware**: Uses sample values to disambiguate (ID vs Code vs Name)
- **Flexible**: Adapts to new schema variations without code changes
- **Intelligent**: Can understand synonyms and abbreviations

### 2. **Why Separate Standard Files?**
- **Explicit Reference**: Clear, authoritative schema definition
- **Version Control**: Can update standards without code changes
- **Multi-Domain**: Different schemas for different domains

### 3. **Why Invert Mapping in Consolidator?**
- **Lookup Efficiency**: For each standard column, find source column
- **Order Preservation**: Standard column order is maintained
- **Missing Column Handling**: Unmapped columns get None

### 4. **Why Source Tracking?**
- **Data Lineage**: Know which file/sheet each row came from
- **Debugging**: Trace issues back to source
- **Audit Trail**: Compliance and validation

### 5. **Why Profile + Mapping + Validation?**
- **Profile**: Understands data structure
- **Mapping**: Transforms structure
- **Validation**: Quality gate before processing

---

## 📝 Summary

This system provides an **intelligent, automated Excel consolidation pipeline** that:
1. ✅ Automatically detects data domains
2. ✅ Intelligently maps columns semantically
3. ✅ Transforms data to standard schemas
4. ✅ Consolidates multiple sources
5. ✅ Produces clean, standardized output files

All powered by AI for flexibility and intelligence, with robust error handling and clear data lineage tracking.
