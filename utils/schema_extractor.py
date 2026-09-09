# utils/schema_extractor.py

import os
import logging
from pathlib import Path
import pandas as pd
import numpy as np

try:
    from rich.console import Console
    console = Console()
except ImportError:
    class DummyConsole:
        def print(self, *args, **kwargs):
            pass
    console = DummyConsole()

logger = logging.getLogger(__name__)

def get_ignored_columns(df: pd.DataFrame) -> list[str]:
    """
    Dynamically identifies columns that should be excluded from unique-value
    and statistical reporting to prevent token bloat and noise in the LLM prompt:
    1. Zero-variance constant columns (nunique <= 1), e.g. EmployeeCount, Over18, StandardHours
    2. Unique identifiers (nunique == total_rows), e.g. EmployeeNumber, Product ID, UUID
    3. High-cardinality text (long descriptions / unique text > 90% unique)
    """
    ignored = []
    total_rows = len(df)
    if total_rows == 0:
        return ignored

    for col in df.columns:
        c_lower = str(col).lower()
        n_unique = df[col].nunique()

        # 1. Zero-variance constant columns (always 1 unique value)
        if n_unique <= 1:
            ignored.append(col)
            continue

        # 2. Unique identifiers (1-to-1 with row count)
        if n_unique == total_rows and total_rows > 10:
            if any(k in c_lower for k in ["id", "number", "num", "key", "code", "uuid", "hash"]) or total_rows > 50:
                ignored.append(col)
                continue

        # 3. High-cardinality text (names, descriptions, titles, free text >90% unique)
        if total_rows > 50 and (n_unique / total_rows) > 0.90:
            if pd.api.types.is_string_dtype(df[col]) or pd.api.types.is_object_dtype(df[col]):
                ignored.append(col)
                continue

    return ignored

def extract_schema(df: pd.DataFrame) -> str:
    """
    Extract data schema, summary stats for numeric columns,
    and unique values for categorical/boolean/date columns using dynamic cardinality filtering.
    """
    logger.info("Extracting schema from dataframe with dynamic cardinality check.")
    schema = ""
    
    # Dynamically detect columns with zero variance or 100% unique IDs
    to_ignore = get_ignored_columns(df)
    
    schema += "Name of data columns:\n"
    for column in df.columns:
        if column in to_ignore:
            continue
        dtype = df[column].dtype
        schema += f"Column: {column}, Type: {dtype}\n"

    # extract numerical columns along with their dtype, mean and std
    numerical_columns = df.select_dtypes(include=['int64', 'int32', 'int16', 'int8', 'float64', 'float32', 'number']).columns
    schema += "\nNumerical columns along with their dtype, mean and std:\n"
    for column in numerical_columns:
        if column in to_ignore:
            continue
        dtype = df[column].dtype
        mean = df[column].mean()
        std = df[column].std()
        mean_str = f"{mean:.2f}" if isinstance(mean, (int, float, np.floating, np.integer)) else str(mean)
        std_str = f"{std:.2f}" if isinstance(std, (int, float, np.floating, np.integer)) else str(std)
        schema += f"Column: {column}, Type: {dtype}, Mean: {mean_str}, Std: {std_str}\n"

    # extract categorical columns along with their dtype and unique values
    categorical_columns = [
        c for c in df.columns 
        if c not in to_ignore and (
            isinstance(df[c].dtype, pd.CategoricalDtype) or 
            pd.api.types.is_string_dtype(df[c]) or 
            pd.api.types.is_object_dtype(df[c])
        )
    ]
    if categorical_columns:
        schema += "\nCategorical columns along with their dtype and unique values:\n"
        for column in categorical_columns:
            dtype = df[column].dtype
            unique_values = df[column].dropna().unique()
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

    return "Data Dictionary: Standard dataset."
