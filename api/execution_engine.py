from api.insights import generate_data_insights
import re
import logging
import traceback
import pandas as pd
import numpy as np
from typing import Any, Dict

from utils.code_safety import strip_code_fences, is_code_safe, validate_python_syntax
from api.config import MAX_RESULT_ROWS

logger = logging.getLogger(__name__)

def detect_chart_type(df: pd.DataFrame) -> Dict[str, Any] | None:
    """
    Intelligently infer the best Plotly chart configuration based on result dataframe columns.
    """
    if df.empty or len(df.columns) < 2:
        return None

    cols = list(df.columns)
    col_types = {col: str(df[col].dtype) for col in cols}
    
    # Identify column categories
    date_cols = [c for c in cols if 'datetime' in col_types[c] or 'date' in c.lower()]
    num_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    cat_cols = [c for c in cols if c not in num_cols and c not in date_cols]

    # Rule 1: Date column + numeric column -> Time Series Line Chart
    if date_cols and num_cols:
        x_col = date_cols[0]
        y_col = num_cols[0]
        sorted_df = df.sort_values(by=x_col)
        return {
            "type": "line",
            "title": f"{y_col.replace('_', ' ')} over Time",
            "x": sorted_df[x_col].astype(str).tolist(),
            "y": sorted_df[y_col].fillna(0).tolist(),
            "x_label": x_col,
            "y_label": y_col
        }

    # Rule 2: Donut / Pie Chart - STRICT PART-TO-WHOLE INTEGRITY
    # Strictly PROHIBIT Pie/Donut charts on averages, means, ratings, or continuous measures (e.g. YearsAtCompany, Age, Income)
    # Pie charts are ONLY permitted on additive part-to-whole quantities (counts, frequencies, or non-mean percentage shares)
    if len(cat_cols) == 1 and len(num_cols) == 1 and len(df) <= 7:
        metric = num_cols[0]
        m_lower = metric.lower()

        is_average_or_rate = any(w in m_lower for w in [
            'mean', 'avg', 'average', 'median', 'year', 'age', 'income',
            'salary', 'rate', 'price', 'cost', 'score', 'rating', 'distance',
            'tenure', 'hour', 'level', 'experience', 'hike'
        ])

        is_count_or_sum = any(w in m_lower for w in [
            'count', 'headcount', 'total', 'sum', 'volume', 'frequency',
            'num_', 'share', 'percent', 'pct'
        ])

        # Only allow pie chart if explicitly an additive count/sum and NOT an average
        if is_count_or_sum and not is_average_or_rate:
            return {
                "type": "pie",
                "title": f"Distribution of {metric.replace('_', ' ')} by {cat_cols[0].replace('_', ' ')}",
                "labels": df[cat_cols[0]].astype(str).tolist(),
                "values": df[metric].fillna(0).tolist()
            }

    # Rule 3: 1 Category + 1 or more Numeric -> Bar Chart
    if (cat_cols or len(cols) == 2) and num_cols:
        x_col = cat_cols[0] if cat_cols else cols[0]
        y_col = num_cols[0]
        return {
            "type": "bar",
            "title": f"{y_col.replace('_', ' ')} by {x_col.replace('_', ' ')}",
            "x": df[x_col].astype(str).tolist(),
            "y": df[y_col].fillna(0).tolist(),
            "x_label": x_col,
            "y_label": y_col
        }

    # Rule 4: 2 Numeric columns -> Scatter Plot
    if len(num_cols) >= 2:
        return {
            "type": "scatter",
            "title": f"{num_cols[1].replace('_', ' ')} vs {num_cols[0].replace('_', ' ')}",
            "x": df[num_cols[0]].fillna(0).tolist(),
            "y": df[num_cols[1]].fillna(0).tolist(),
            "x_label": num_cols[0],
            "y_label": num_cols[1]
        }

    return None

def execute_generated_code(code: str, df: pd.DataFrame, query: str = "") -> Dict[str, Any]:
    """
    Safely execute the LLM-generated code against DataFrame 'df'.
    Validates safety, syntax, and captures the 'result' output.
    """
    clean_code = strip_code_fences(code)

    # 1. Security Check
    if not is_code_safe(clean_code):
        logger.warning(f"Rejected unsafe code: {clean_code}")
        return {
            "success": False,
            "error_type": "SecurityViolation",
            "error": "Generated code violated safety policy (disallowed imports or system calls).",
            "code": clean_code
        }

    # 2. Syntax Validation
    is_valid_syntax, syntax_err = validate_python_syntax(clean_code)
    if not is_valid_syntax:
        return {
            "success": False,
            "error_type": "SyntaxError",
            "error": syntax_err,
            "code": clean_code
        }

    # 3. Execution Environment
    # Prepare local execution namespace
    local_scope: Dict[str, Any] = {
        "df": df,
        "pd": pd,
        "np": np
    }

    try:
        # If the code does not assign to 'result', wrap the last line if it's an expression
        lines = [line for line in clean_code.split("\n") if line.strip() and not line.strip().startswith("#")]
        if lines and not any("result" in l.split("=")[0] for l in lines if "=" in l):
            last_line = lines[-1].strip()
            # If last line does not look like assignment
            if not ("=" in last_line and not any(op in last_line for op in ["==", ">=", "<=", "!="])):
                modified_lines = lines[:-1] + [f"result = ({last_line})"]
                exec_code = "\n".join(modified_lines)
            else:
                exec_code = clean_code
        else:
            exec_code = clean_code

        exec(exec_code, {"__builtins__": {
            "len": len, "range": range, "list": list, "dict": dict, "set": set,
            "int": int, "float": float, "str": str, "bool": bool, "round": round,
            "min": min, "max": max, "sum": sum, "abs": abs, "zip": zip,
            "enumerate": enumerate, "isinstance": isinstance, "sorted": sorted,
            "print": lambda *args: None
        }}, local_scope)

        result = local_scope.get("result", None)

        # 4. Format Output
        if result is None:
            return {
                "success": True,
                "code": clean_code,
                "result_type": "none",
                "message": "Code executed successfully, but no result was returned."
            }

        # Convert Series to DataFrame
        if isinstance(result, pd.Series):
            result = result.reset_index()

        if isinstance(result, pd.DataFrame):
            total_rows = len(result)
            truncated_df = result.head(MAX_RESULT_ROWS)
            
            # Serialize columns and records safely
            records = truncated_df.replace({np.nan: None}).to_dict(orient="records")
            # Convert timestamp or categorical items to serializable formats
            for r in records:
                for k, v in r.items():
                    if isinstance(v, (pd.Timestamp, np.datetime64)):
                        r[k] = str(v)
                    elif isinstance(v, (np.integer, int)):
                        r[k] = int(v)
                    elif isinstance(v, (np.floating, float)):
                        r[k] = round(float(v), 2)

            chart_config = detect_chart_type(result)
            insights = generate_data_insights(query, result, chart_config)

            return {
                "success": True,
                "code": clean_code,
                "result_type": "dataframe",
                "total_rows": total_rows,
                "displayed_rows": len(records),
                "columns": list(result.columns),
                "data": records,
                "chart": chart_config,
                "insights": insights
            }

        # Scalar or simple collection
        if isinstance(result, (int, float, np.number)):
            formatted_val = round(float(result), 2) if isinstance(result, (float, np.floating)) else int(result)
            return {
                "success": True,
                "code": clean_code,
                "result_type": "scalar",
                "value": formatted_val,
                "display": f"{formatted_val:,}"
            }

        if isinstance(result, (dict, list)):
            return {
                "success": True,
                "code": clean_code,
                "result_type": "json",
                "value": result
            }

        return {
            "success": True,
            "code": clean_code,
            "result_type": "text",
            "value": str(result)
        }

    except Exception as e:
        logger.error(f"Execution failed: {traceback.format_exc()}")
        return {
            "success": False,
            "error_type": type(e).__name__,
            "error": str(e),
            "code": clean_code
        }
