import os
import logging
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

from api.data_loader import dataset_manager
from api.agent import generate_pandas_code
from api.execution_engine import execute_generated_code
from api.config import PUBLIC_DIR, MAX_UPLOAD_BYTES

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Data Analytics AI Agent",
    description="Natural Language Data Interrogation & Safe Pandas Execution Engine (10MB Dataset Ready)",
    version="1.0.0"
)

# Enable CORS for local development and Vercel preview domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request models
class QueryRequest(BaseModel):
    query: str
    api_key: Optional[str] = None

class UrlLoadRequest(BaseModel):
    url: str

class DirectCodeExecuteRequest(BaseModel):
    code: str

# API Endpoints
@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "dataset": dataset_manager.dataset_name,
        "rows": len(dataset_manager.df) if dataset_manager.df is not None else 0
    }

@app.get("/api/info")
def get_dataset_info():
    """Return dataset overview, columns, schema, summary, and data dictionary."""
    return dataset_manager.get_info()

@app.post("/api/query")
def run_query(payload: QueryRequest):
    """
    Accepts user question, generates pandas code using LLM (with schema & context),
    checks code safety, executes on df, and returns data and chart config.
    """
    if not payload.query or not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query string cannot be empty.")

    if dataset_manager.df is None:
        raise HTTPException(status_code=500, detail="No active dataset loaded.")

    try:
        # 1. Generate code
        agent_res = generate_pandas_code(
            user_query=payload.query.strip(),
            df=dataset_manager.df,
            schema=dataset_manager.schema,
            summary=dataset_manager.summary,
            data_dictionary=dataset_manager.data_dictionary,
            custom_api_key=payload.api_key or ""
        )

        generated_code = agent_res["code"]
        provider = agent_res["provider"]
        note = agent_res["note"]

        # 2. Safely execute code
        exec_res = execute_generated_code(generated_code, dataset_manager.df)

        return {
            "query": payload.query,
            "provider": provider,
            "note": note,
            "execution": exec_res
        }
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/execute-code")
def run_custom_code(payload: DirectCodeExecuteRequest):
    """
    Directly execute user-provided code with safety verification.
    """
    if dataset_manager.df is None:
        raise HTTPException(status_code=500, detail="No active dataset loaded.")

    exec_res = execute_generated_code(payload.code, dataset_manager.df)
    return {"execution": exec_res}

@app.post("/api/upload")
async def upload_dataset(file: UploadFile = File(...)):
    """Upload a custom CSV or Parquet dataset (up to 10MB)."""
    try:
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum allowed limit of {MAX_UPLOAD_BYTES // (1024*1024)}MB."
            )
        info = dataset_manager.load_from_bytes(content, file.filename)
        return {"status": "success", "message": f"Successfully loaded {file.filename}", "dataset": info}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to parse dataset: {str(e)}")

@app.post("/api/load-url")
def load_from_url(payload: UrlLoadRequest):
    """Load dataset from a public URL."""
    try:
        info = dataset_manager.load_from_url(payload.url)
        return {"status": "success", "message": f"Successfully loaded dataset from URL", "dataset": info}
    except Exception as e:
        logger.error(f"Failed to load URL {payload.url}: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/reset")
def reset_to_default():
    """Reset to the default retail sample dataset."""
    dataset_manager.load_default()
    return {"status": "success", "message": "Reset to default sample dataset", "dataset": dataset_manager.get_info()}

# Serve static frontend for local Uvicorn development
if PUBLIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(PUBLIC_DIR)), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(PUBLIC_DIR / "index.html")

    @app.get("/{full_path:path}")
    def serve_spa_or_file(full_path: str):
        target = PUBLIC_DIR / full_path
        if target.exists() and target.is_file():
            return FileResponse(target)
        return FileResponse(PUBLIC_DIR / "index.html")
