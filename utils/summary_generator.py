# utils/summary_generator.py

import logging
try:
    from rich.console import Console
    console = Console()
except ImportError:
    class DummyConsole:
        def print(self, *args, **kwargs):
            pass
    console = DummyConsole()

logger = logging.getLogger(__name__)

def generate_summary(df):
    """
    Generate comprehensive statistical summary of the dataframe.
    """
    logger.info("Generating summary of dataframe.")
    try:
        summary = df.describe(include='all').to_string()
    except Exception as e:
        logger.warning(f"Error in include='all' describe: {e}, falling back to numeric describe")
        summary = df.describe().to_string()
    logger.debug(f"Generated summary: {summary}")
    return summary
