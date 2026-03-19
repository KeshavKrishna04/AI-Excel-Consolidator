"""
FastAPI application for the AI Excel Consolidator.

Run with: uvicorn api.main:app --reload

Endpoints:
- GET /          - API info
- GET /health    - Health check
- POST /consolidate - Upload Excel files, run consolidation, download result
"""

import io
import os
import tempfile
import contextlib
from typing import Annotated, List

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Import the pipeline from main - no changes to consolidation logic
from main import run_pipeline
from graph.qa_graph import build_qa_graph

OUTPUT_DIR = "outputs"
OUTPUT_FILENAME = "consolidated_output.xlsx"

QA_WORKBOOK_PATH = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)
qa_graph = build_qa_graph()


class QARequest(BaseModel):
    """Request body for the /ask endpoint."""

    question: str


app = FastAPI(
    title="AI Excel Consolidator API",
    description="Consolidate vendor Excel files into a standardized output using AI-powered schema mapping.",
    version="1.0.0",
)


def _patch_openapi_for_file_arrays(schema: dict) -> dict:
    """
    Swagger UI in some environments doesn't render file pickers for OpenAPI 3.1
    `contentMediaType` file schemas. Patch those to the older, widely-supported
    `format: binary` representation.
    """
    components = schema.get("components", {})
    schemas = components.get("schemas", {}) if isinstance(components, dict) else {}

    for _, s in schemas.items():
        if not isinstance(s, dict):
            continue
        props = s.get("properties")
        if not isinstance(props, dict):
            continue
        for prop_name, prop_schema in props.items():
            if prop_name != "files" or not isinstance(prop_schema, dict):
                continue
            items = prop_schema.get("items")
            if isinstance(items, dict) and items.get("type") == "string":
                # Replace OpenAPI 3.1 file hint with classic binary format.
                items.pop("contentMediaType", None)
                items["format"] = "binary"
    return schema


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema = _patch_openapi_for_file_arrays(schema)
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[assignment]


@app.get("/")
def root():
    """API info and usage."""
    return {
        "name": "AI Excel Consolidator API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "consolidate": "POST /consolidate - Upload Excel files, get consolidated output",
    }


@app.get("/health")
def health():
    """Health check for load balancers and monitoring."""
    return {"status": "ok"}


@app.post("/consolidate")
def consolidate(files: Annotated[List[UploadFile], File(...)]):
    """
    Upload one or more Excel files (.xlsx, .xls), run the consolidation pipeline,
    and return the consolidated output workbook.

    Standard schema reference files (sales.xlsx, nielsen.xlsx, etc.) must exist
    in the data/ directory. Only vendor/input files are uploaded here.
    """
    if not files:
        raise HTTPException(
            status_code=400,
            detail="At least one Excel file must be uploaded.",
        )

    # Validate file extensions
    allowed = {".xlsx", ".xls"}
    invalid = []
    for f in files:
        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext not in allowed:
            invalid.append(f.filename or "(unnamed)")
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type(s). Allowed: .xlsx, .xls. Invalid: {invalid}",
        )

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        vendor_files = []

        for upload in files:
            path = os.path.join(temp_dir, upload.filename or "upload.xlsx")
            content = upload.file.read()
            with open(path, "wb") as f:
                f.write(content)
            vendor_files.append(path)

        # Capture stdout so pipeline logs don't pollute API response
        stdout_capture = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout_capture):
                run_pipeline(vendor_files)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Consolidation failed: {str(e)}",
            ) from e

    out_path = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)

    if not os.path.exists(out_path):
        raise HTTPException(
            status_code=500,
            detail="Pipeline completed but output file was not created.",
        )

    return FileResponse(
        path=out_path,
        filename=OUTPUT_FILENAME,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/ask")
def ask_question(payload: QARequest):
    """
    Ask a natural-language question about the latest consolidated_output.xlsx.

    This endpoint:
    - ensures the consolidated workbook exists
    - runs a LangGraph workflow that summarizes the workbook
      and uses an LLM-backed agent to answer the question
    """
    # Allow any supported dataset format in outputs/ (xlsx/csv/txt/clean).
    # The graph will resolve the actual dataset file.
    if not os.path.exists(OUTPUT_DIR):
        raise HTTPException(
            status_code=400,
            detail=(
                "No outputs/ folder found. Run POST /consolidate first to generate a dataset, "
                "or place a supported dataset file in outputs/."
            ),
        )

    try:
        result_state = qa_graph.invoke(
            {
                "question": payload.question,
                # Pass the folder; graph will pick the first supported dataset file within.
                "workbook_path": OUTPUT_DIR,
            }
        )
    except FileNotFoundError as e:
        # Workbook missing or removed between existence check and load
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        # Unexpected processing errors
        raise HTTPException(
            status_code=500,
            detail=f"Failed to answer question over consolidated workbook: {e}",
        ) from e

    status = result_state.get("status", "error")
    answer = result_state.get("answer", "")
    reason = result_state.get("reason")

    # Standard JSON response so it's easy to use from terminal or other clients
    response_payload = {
        "status": status,
        "answer": answer,
    }
    if reason:
        response_payload["reason"] = reason

    # For out-of-scope questions, return 200 with explicit status so callers
    # can decide how to handle it.
    return response_payload
