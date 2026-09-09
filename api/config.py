import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PUBLIC_DIR = BASE_DIR / "public"

# Load .env file manually if exists
env_file = BASE_DIR / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

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
