# utils/data_loader.py

import pandas as pd
import logging
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)

def load_csv(filepath):
    logger.info(f"Loading CSV file from '{filepath}'")
    try:
        df = pd.read_csv(filepath)
        logger.info(f"Loaded dataframe with shape {df.shape}")
        return df
    except Exception as e:
        logger.error(f"Error loading CSV file: {e}")
        return None
