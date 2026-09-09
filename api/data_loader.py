import ssl

def get_ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    except Exception:
        return ssl._create_unverified_context()

import os
import io
import urllib.request
import logging
import pandas as pd
import numpy as np
from pathlib import Path

from utils.schema_extractor import extract_schema, extract_data_dictionary
from utils.summary_generator import generate_summary
from api.config import DEFAULT_DATASET_PATH, MAX_UPLOAD_BYTES

logger = logging.getLogger(__name__)

class DatasetManager:
    """
    Manages the active DataFrame in memory, providing schema extraction,
    summary generation, memory optimization, and dataset switching.
    """
    def __init__(self):
        self.df: pd.DataFrame | None = None
        self.dataset_name: str = "sample_retail_data.csv"
        self.schema: str = ""
        self.summary: str = ""
        self.data_dictionary: str = ""
        self.load_default()

    def optimize_memory(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Downcast numerical columns and convert low-cardinality strings
        to category to ensure the 10MB dataset stays lightweight in RAM (<30MB).
        """
        initial_mem = df.memory_usage(deep=True).sum() / (1024 * 1024)
        for col in df.columns:
            dtype = df[col].dtype
            # Optimize floats
            if dtype == 'float64':
                df[col] = pd.to_numeric(df[col], downcast='float')
            # Optimize integers
            elif dtype == 'int64':
                df[col] = pd.to_numeric(df[col], downcast='integer')
            # Convert low-cardinality string columns to category
            elif dtype == 'object':
                num_unique = df[col].nunique()
                num_total = len(df[col])
                if num_total > 0 and (num_unique / num_total) < 0.5 and num_unique < 500:
                    df[col] = df[col].astype('category')
            # Detect dates
            elif 'date' in col.lower() and dtype == 'object':
                try:
                    df[col] = pd.to_datetime(df[col])
                except Exception:
                    pass

        final_mem = df.memory_usage(deep=True).sum() / (1024 * 1024)
        logger.info(f"Optimized DataFrame memory from {initial_mem:.2f}MB to {final_mem:.2f}MB")
        return df

    def update_metadata(self):
        """Extract and cache schema, summary, and data dictionary."""
        if self.df is not None:
            self.schema = extract_schema(self.df)
            self.summary = generate_summary(self.df)
            self.data_dictionary = extract_data_dictionary(self.df)

    def load_default(self):
        """Load the bundled default retail sales dataset."""
        if os.path.exists(DEFAULT_DATASET_PATH):
            df = pd.read_csv(DEFAULT_DATASET_PATH)
            self.df = self.optimize_memory(df)
            self.dataset_name = "sample_retail_data.csv"
            self.update_metadata()
            logger.info(f"Loaded default dataset: {len(self.df)} rows, {len(self.df.columns)} columns")
        else:
            # Create a tiny in-memory dataframe if file missing
            self.df = pd.DataFrame({
                "store": ["Store #101", "Store #102"],
                "Brand": ["PureBrew", "NutriFarm"],
                "Revenue": [1200.5, 950.0],
                "Units_Sold": [120, 95]
            })
            self.dataset_name = "minimal_fallback.csv"
            self.update_metadata()

    def load_from_bytes(self, file_bytes: bytes, filename: str) -> dict:
        """Load a CSV/Parquet from uploaded file bytes (up to 10MB)."""
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            raise ValueError(f"File exceeds maximum allowed size of {MAX_UPLOAD_BYTES // (1024*1024)}MB")

        if filename.endswith(".parquet"):
            df = pd.read_parquet(io.BytesIO(file_bytes))
        else:
            df = pd.read_csv(io.BytesIO(file_bytes))

        self.df = self.optimize_memory(df)
        self.dataset_name = filename
        self.update_metadata()
        return self.get_info()

    def load_from_url(self, url: str) -> dict:
        """Download and load dataset from a remote URL."""
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=15, context=get_ssl_context()) as response:
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) > MAX_UPLOAD_BYTES:
                raise ValueError(f"Remote dataset exceeds maximum size of {MAX_UPLOAD_BYTES // (1024*1024)}MB")
            file_bytes = response.read(MAX_UPLOAD_BYTES + 1)
            if len(file_bytes) > MAX_UPLOAD_BYTES:
                raise ValueError("Remote dataset exceeds maximum size limit")

        filename = url.split("?")[0].split("/")[-1] or "remote_dataset.csv"
        return self.load_from_bytes(file_bytes, filename)

    def get_info(self) -> dict:
        """Return metadata for the active dataset."""
        if self.df is None:
            return {"status": "no_data"}

        mem_mb = self.df.memory_usage(deep=True).sum() / (1024 * 1024)
        sample_records = self.df.head(10).to_dict(orient="records")
        columns_info = [{"name": c, "type": str(self.df[c].dtype)} for c in self.df.columns]

        return {
            "dataset_name": self.dataset_name,
            "rows": len(self.df),
            "columns_count": len(self.df.columns),
            "memory_mb": round(mem_mb, 2),
            "columns": columns_info,
            "schema": self.schema,
            "summary": self.summary,
            "data_dictionary": self.data_dictionary,
            "sample_rows": sample_records
        }

# Global singleton dataset manager
dataset_manager = DatasetManager()
