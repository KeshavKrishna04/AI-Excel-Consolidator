# AI Excel Consolidator (LangGraph-powered)

This project consolidates **multiple vendor Excel files with different schemas** into a single standardized output workbook: `outputs/consolidated_output.xlsx`.

It uses LLM-backed agents to:
- **Detect the domain** of each sheet (sales / nielsen / pricing / competitor / baseline)
- **Generate a semantic column mapping** from vendor columns → standard columns
- **Optionally split “combined columns”** (e.g. `"(customer_name, customer_code)"`)
- **Validate** whether the sheet is usable for the detected domain
- **Consolidate** rows into a per-domain standardized DataFrame with full lineage (`source_file`, `source_sheet`)

The per-sheet workflow is implemented as a **LangGraph graph** (nodes + edges) so the pipeline is explicit, traceable, and easy to extend.

---

## 🎯 What you get

- **Input**: any number of vendor Excel files, each with 1+ sheets, each sheet can have a different schema.
- **Output**: one workbook at `outputs/consolidated_output.xlsx` containing:
  - `Consolidated_Sales`
  - `Consolidated_Nielsen`
  - `Consolidated_Pricing`
  - `Consolidated_Competitor`
  - `Consolidated_Baseline`
  - (or a fallback `Consolidation_Info` sheet if nothing could be consolidated)

---

## ⚙️ Installation

### Prerequisites

- Python 3.9+ recommended
- `pip`

### Setup (Windows PowerShell)

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

---

## 📦 Dependencies

Dependencies are tracked in `requirements.txt`. The key ones are:

- **pandas / openpyxl**: Excel I/O and dataframe operations
- **openai + python-dotenv**: OpenAI-compatible LLM access via `.env`
- **streamlit**: Web UI
- **fastapi + uvicorn**: REST API server
- **langgraph**: workflow orchestration (the per-sheet graph)
- **langchain + langchain-openai**: installed for future/optional LLM plumbing improvements (see “LangChain implementation” below)

---

## 🔐 Environment variables (LLM)

This project uses an **OpenAI-compatible** client (works with OpenAI, OpenRouter, and other compatible gateways).

Create a `.env` file in the project root with:

```bash
OPENAI_API_BASE=https://openrouter.ai/api/v1
OPENAI_API_KEY=your_key_here
```

Notes:
- The code reads these in `llm/openrouter_client.py`.
- The agents currently call `model="openai/gpt-4o-mini"` (as a provider/model id used by your gateway).

---

## 🚀 How to run

### Option A: CLI (batch mode)

1. Put the standard reference schema files in `data/`:
   - `data/sales.xlsx`
   - `data/nielsen.xlsx`
   - `data/pricing.xlsx`
   - `data/competitor.xlsx`
   - `data/baseline.xlsx`
2. Put vendor files in `data/` as well (any names, any schemas).
3. Run:

```bash
python main.py
```

Output:
- `outputs/consolidated_output.xlsx`

### Option B: Streamlit UI

```bash
streamlit run app.py
```

Upload one or more Excel files and click **Consolidate**. The UI calls the same pipeline and serves `outputs/consolidated_output.xlsx` for download.

### Option C: FastAPI (REST API)

1. Ensure standard schema files exist in `data/` (same as CLI).
2. From the project root:

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

- **API docs**: http://localhost:8000/docs
- **Health**: GET http://localhost:8000/health
- **Consolidate**: POST http://localhost:8000/consolidate with Excel files (multipart form: `files`)

Example with curl:

```bash
curl -X POST "http://localhost:8000/consolidate" -F "files=@data/vendor1.xlsx" -F "files=@data/vendor2.xlsx" -o consolidated_output.xlsx
```

---

## 🔄 End-to-end control flow (from input → output)

There are three entrypoints:
- **CLI**: `main.py` (`if __name__ == "__main__":`)
- **Streamlit UI**: `app.py` → calls `main.run_pipeline(vendor_files)`
- **FastAPI**: `api/main.py` → calls `main.run_pipeline(vendor_files)` for POST /consolidate

### Step 0: Vendor file discovery (CLI mode)

In CLI mode, `main.py` scans `data/` for `*.xlsx` and **excludes** the five standard schema files so only vendor files are processed.

### Step 1: Load standard schemas (once per run)

`main.load_all_standard_schemas()`:
- Iterates `STANDARD_FILES` in `main.py`
- For each standard reference file, calls:
  - `core.standard_parser.extract_standard_schemas(path)`
- Produces a dict:
  - `schemas[domain] = [ordered list of standard columns]`

This `schemas` dict is treated as **authoritative** (we never “invent” new standard columns).

### Step 2: For each vendor file → load all non-empty sheets

`core.excel_loader.load_excel_sheets(vendor_file)`:
- `pd.read_excel(path, sheet_name=None)` reads all sheets
- empty sheets are dropped
- returns: `[(sheet_name, df), ...]`

### Step 3: For each sheet → run the LangGraph workflow

For each sheet, `main.run_pipeline` builds an `initial_state` and runs:

- `result_state = sheet_graph.invoke(initial_state)`
- `consolidated = result_state.get("consolidated", consolidated)`

The **graph decides**:
- whether to stop early (unsupported domain / validation reject), or
- to consolidate the sheet into the correct domain DataFrame.

### Step 4: Post-processing enrichment (optional)

After all sheets:
- if sales has `city` and `state`, `agents/enrichment_agent.enrich_state_from_city` fills missing state values (India-specific).

### Step 5: Write output workbook

`core.excel_writer.write_multisheet_excel(...)` writes:
- `outputs/consolidated_output.xlsx`
- with per-domain sheets (only those that have data)
- or a fallback `Consolidation_Info` if nothing was consolidated

---

## 📊 End-to-end data flow (objects and transformations)

At runtime, the main objects are:

- **Vendor DataFrame** (`df`)
  - raw vendor columns, raw vendor values

- **Profile dict** (`profile`)
  - created by `agents/schema_agent.profile_sheet(df)`
  - compact summary sent to LLMs:
    - dtypes
    - a few sample values per column
    - optional numeric hints

- **Domain info** (`domain_info`)
  - created by `agents/domain_agent.detect_domain(...)`

- **Mapping** (`mapping`)
  - created by `agents/mapping_agent.generate_schema_mapping(...)`
  - format:
    - `{vendor_column: standard_column}`

- **Splits config** (`splits_config`)
  - optional output from mapping agent
  - drives `core/column_splitter.apply_column_splits(...)`
  - adds new columns to the vendor DataFrame (targets)

- **Consolidated DataFrames**
  - dict: `consolidated[domain] -> DataFrame`
  - standardized schema:
    - `[standard_columns..., "source_file", "source_sheet"]`

---

## 🧩 LangGraph implementation (detailed)

### Where it’s implemented

- **Graph definition**: `graph/sheet_graph.py`
- **Graph builder**: `build_sheet_graph()`
- **Graph invocation**: `main.py` inside `run_pipeline(...)`

### What the graph does

The graph processes **one sheet at a time** and updates a running accumulator (`consolidated`) inside the state.

### Graph state (`SheetState`)

`SheetState` is a `TypedDict` that can contain keys like:
- `sheet_name`, `df`
- `profile`
- `domain_info`, `domain`
- `mapping`, `splits_config`
- `df_to_consolidate`
- `validation`
- `schemas`
- `consolidated`
- `source_file`, `source_sheet`

### Nodes and their responsibilities

- **`profile`**
  - Input: `df`
  - Output: `profile`
  - Calls: `agents/schema_agent.profile_sheet`

- **`detect_domain`**
  - Input: `sheet_name`, `df.columns`, `profile`
  - Output: `domain_info`, `domain`
  - Calls: `agents/domain_agent.detect_domain`

- **`generate_mapping`**
  - Input: `profile`, `schemas[domain]`, `domain`
  - Output: `mapping`, `splits_config`
  - Calls: `agents/mapping_agent.generate_schema_mapping`

- **`apply_splits`**
  - If `splits_config` exists:
    - Calls `core/column_splitter.apply_column_splits`
    - Updates `mapping` so the consolidator reads the newly created columns
    - Re-profiles `df_to_consolidate` to help validation
  - Output: `df_to_consolidate` (and updated `mapping`, updated `profile`)

- **`validate`**
  - Input: `profile`, `mapping`, `domain`
  - Output: `validation`
  - Calls: `agents/validation_agent.validate_sheet`

- **`consolidate`**
  - Input: `mapping`, `df_to_consolidate`, `schemas[domain]`, `consolidated[domain]`
  - Output: updated `consolidated`
  - Calls: `core/consolidator.consolidate_domain_data`

### Edges and routing

The graph is:

```
profile → detect_domain → (conditional)
  - unsupported → END
  - continue    → generate_mapping → apply_splits → validate → (conditional)
                   - reject → END
                   - accept → consolidate → END
```

What this buys you:
- “Skip sheet” is a graph route, not nested imperative control flow.
- The workflow is explicit and easy to extend.

---

## 🔗 LangChain implementation (what’s used, what’s available)

This repo installs **LangChain + langchain-openai**, but the current agent modules still use the OpenAI SDK directly:
- `llm/openrouter_client.py` returns an OpenAI-compatible client.
- `agents/*.py` call `client.chat.completions.create(...)`.

So today:
- **LangGraph**: actively used (orchestration).
- **LangChain**: available to adopt incrementally (structured outputs, retries, model abstraction), but not required for the pipeline to work.

---

## 📁 Folder-by-folder / file-by-file explanation

### Root

- **`main.py`**
  - CLI entrypoint + pipeline orchestration
  - loads standard schemas
  - runs the per-sheet LangGraph
  - runs optional enrichment
  - writes `outputs/consolidated_output.xlsx`

- **`app.py`**
  - Streamlit UI
  - writes uploads to a temp directory
  - calls `run_pipeline`
  - reads the output workbook and provides preview + download

- **`requirements.txt`**
  - pinned/declared Python dependencies
  - includes LangGraph/LangChain dependencies

### `graph/`

- **`sheet_graph.py`**
  - LangGraph workflow for a single sheet
  - nodes, edges, and routing logic

### `api/`

- **`main.py`**
  - FastAPI application
  - Endpoints: `/`, `/health`, POST `/consolidate`
  - Accepts Excel file uploads, runs `run_pipeline`, returns consolidated output

### `core/`

- **`excel_loader.py`**
  - read vendor Excel files into DataFrames
  - trims column whitespace
  - skips empty sheets

- **`standard_parser.py`**
  - reads standard schema reference files and extracts column order

- **`column_splitter.py`**
  - splits combined columns into multiple target columns
  - driven by `splits_config` from the mapping agent

- **`consolidator.py`**
  - maps vendor rows into standard columns
  - adds lineage columns (`source_file`, `source_sheet`)
  - appends into the consolidated DataFrame

- **`excel_writer.py`**
  - writes a single workbook with multiple sheets
  - enforces Excel-safe sheet names

### `agents/`

- **`schema_agent.py`**: profiles columns + sample values
- **`domain_agent.py`**: LLM domain classification
- **`mapping_agent.py`**: LLM mapping + optional split detection
- **`validation_agent.py`**: LLM validation / quality gate
- **`enrichment_agent.py`**: optional sales enrichment (state from city)

### `llm/`

- **`openrouter_client.py`**
  - loads `.env`
  - creates OpenAI-compatible client with base URL + API key

- **`json_utils.py`**
  - extracts JSON from LLM output robustly

### `config/`

- **`domains.py`**
  - declares supported domains

### `data/`

- holds:
  - five standard schema reference files
  - vendor files you want to process

### `outputs/`

- contains:
  - `consolidated_output.xlsx` produced by the pipeline

---

## 🧪 Scalability notes (rows: 50 → 500k+)

- LLM calls are based on small **profiles**, not raw rows, so token usage stays bounded.
- The heavy work is local:
  - Excel read/write (openpyxl)
  - DataFrame processing (pandas)
- If you later hit performance limits, the first optimization target is `core/consolidator.py`, which currently maps row-by-row (can be vectorized).

---

## 📖 Additional documentation

- `PROJECT_EXPLANATION.md` contains the earlier deep-dive narrative.
  - This README is the up-to-date reference for the **LangGraph-based** implementation.

