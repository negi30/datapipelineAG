# utils/schema_extractor.py

import os
import logging
from pathlib import Path

try:
    from rich.console import Console
    console = Console()
except ImportError:
    class DummyConsole:
        def print(self, *args, **kwargs):
            pass
    console = DummyConsole()

logger = logging.getLogger(__name__)

def extract_schema(df):
    """
    Extract data schema, summary stats for numeric columns,
    and unique values for categorical/boolean/date columns.
    """
    logger.info("Extracting schema from dataframe.")
    schema = ""
    # add name of all columns to schema
    to_ignore = ["store", "Product ID", "Product Title", "Brand", "Unit", "Quantity Per Case", "State", "City", "District"]
    
    schema += "Name of data columns:\n"
    for column in df.columns:
        if column in to_ignore:
            continue
        dtype = df[column].dtype
        schema += f"Column: {column}, Type: {dtype}\n"

    # extract numerical columns along with their dtype, mean and std
    numerical_columns = df.select_dtypes(include=['int64', 'int32', 'int16', 'float64', 'float32', 'number']).columns
    schema += "\nNumerical columns along with their dtype, mean and std:\n"
    for column in numerical_columns:
        if column in to_ignore:
            continue
        dtype = df[column].dtype
        mean = df[column].mean()
        std = df[column].std()
        schema += f"Column: {column}, Type: {dtype}, Mean: {mean:.2f} if isinstance(mean, (int, float)) else mean, Std: {std:.2f} if isinstance(std, (int, float)) else std\n"

    # extract categorical columns along with their dtype and unique values
    categorical_columns = df.select_dtypes(include=['object', 'category', 'string']).columns
    schema += "\nCategorical columns along with their dtype and unique values:\n"
    for column in categorical_columns:
        if column in to_ignore:
            continue
        dtype = df[column].dtype
        unique_values = df[column].unique()
        if len(unique_values) > 20:
            unique_display = f"Sample of {len(unique_values)} unique values: {list(unique_values[:15])}..."
        else:
            unique_display = f"Unique Values: {list(unique_values)}"
        schema += f"Column: {column}, Type: {dtype}, {unique_display}\n"

    # extract boolean columns along with their dtype and unique values
    boolean_columns = df.select_dtypes(include=['bool']).columns
    if len(boolean_columns) > 0:
        schema += "\nBoolean columns along with their dtype and unique values:\n"
        for column in boolean_columns:
            if column in to_ignore:
                continue
            dtype = df[column].dtype
            unique_values = df[column].unique()
            schema += f"Column: {column}, Type: {dtype}, Unique Values: {list(unique_values)}\n"

    # extract date columns along with their dtype and unique values
    date_columns = df.select_dtypes(include=['datetime64', 'datetime']).columns
    if len(date_columns) > 0:
        schema += "\nDate columns along with their dtype and unique values:\n"
        for column in date_columns:
            if column in to_ignore:
                continue
            dtype = df[column].dtype
            unique_values = df[column].unique()
            schema += f"Column: {column}, Type: {dtype}, Unique Values: {list(unique_values[:10])}\n"

    schema = schema.strip()
    return schema

def extract_data_dictionary(df=None, filepath="data_dictionary.txt"):
    """
    Load data dictionary from data_dictionary.txt, data/data_dictionary.txt,
    or current directory.
    """
    logger.info("Extracting data dictionary from dataframe.")
    data_dictionary = ""
    candidate_paths = [
        filepath,
        os.path.join(os.path.dirname(__file__), "..", "data", "data_dictionary.txt"),
        os.path.join(os.path.dirname(__file__), "..", "data_dictionary.txt"),
        Path.cwd() / "data" / "data_dictionary.txt",
        Path.cwd() / "data_dictionary.txt"
    ]
    for path in candidate_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as file:
                    data_dictionary = file.read()
                logger.info(f"Loaded data dictionary from {path}")
                return data_dictionary
            except Exception as e:
                logger.warning(f"Error reading {path}: {e}")

    # Fallback if no file found yet
    return "Data Dictionary: Standard business dataset with product, store, revenue, and geographical attributes."
