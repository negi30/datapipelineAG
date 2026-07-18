# utils/summary_generator.py

import logging
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)

def generate_summary(df):
    logger.info("Generating summary of dataframe.")
    summary = df.describe(include='all').to_string()
    logger.debug(f"Generated summary: {summary}")
    return summary
