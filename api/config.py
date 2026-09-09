import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PUBLIC_DIR = BASE_DIR / "public"

# Dataset Settings
MAX_DATASET_MB = int(os.environ.get("MAX_DATASET_MB", 10))
MAX_UPLOAD_BYTES = MAX_DATASET_MB * 1024 * 1024
DEFAULT_DATASET_PATH = DATA_DIR / "sample_retail_data.csv"

# LLM Keys
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Execution Limits
EXECUTION_TIMEOUT_SECONDS = int(os.environ.get("EXECUTION_TIMEOUT_SECONDS", 10))
MAX_RESULT_ROWS = int(os.environ.get("MAX_RESULT_ROWS", 250))
