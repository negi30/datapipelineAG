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

INDEX_LIKE_COLS = {"index", "level_0", "unnamed: 0", "_index"}

def clean_dataframe_indices(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure the DataFrame has a clean tabular structure.
    Only resets index if it has a meaningful name or is a MultiIndex.
    Strips raw numeric row index artifacts so they are never confused with business metrics.
    """
    if df.empty:
        return df

    if df.index.name is not None or isinstance(df.index, pd.MultiIndex):
        df = df.reset_index()
        df.columns.name = None
    else:
        df = df.reset_index(drop=True)

    # Drop any accidental metadata index column if other columns exist
    for col in list(df.columns):
        if str(col).lower() in INDEX_LIKE_COLS and len(df.columns) > 1 and pd.api.types.is_numeric_dtype(df[col]):
            df = df.drop(columns=[col])

    return df

def detect_chart_type(df: pd.DataFrame, query: str = "") -> Dict[str, Any] | None:
    """
    Intelligently infer the best Plotly chart configuration based on result dataframe columns and query context.
    Prevents self-mapping bugs, properly identifies scatter plots, and guards against rendering walls.
    """
    if df.empty:
        return None

    df = clean_dataframe_indices(df)

    if len(df.columns) < 2:
        return None

    cols = list(df.columns)
    col_types = {col: str(df[col].dtype) for col in cols}
    
    # Identify column categories (exclude metadata index/id columns)
    date_cols = [c for c in cols if ('datetime' in col_types[c] or 'date' in str(c).lower()) and str(c).lower() not in INDEX_LIKE_COLS]
    num_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c]) and str(c).lower() not in INDEX_LIKE_COLS]
    cat_cols = [c for c in cols if c not in num_cols and c not in date_cols and str(c).lower() not in INDEX_LIKE_COLS]

    q_lower = (query or "").lower()
    is_scatter_query = any(w in q_lower for w in ["scatter", "s plot", "relationship", "correlation", "vs", "versus"])

    # Rule 1: Explicit Scatter Query or 2+ Numeric Columns with No Categories or High Row Count (>30)
    # Prevents the "Self-Mapping Bug" and 11,000-bar rendering wall
    if len(num_cols) >= 2 and (not cat_cols or is_scatter_query or len(df) > 30):
        x_col = num_cols[0]
        y_col = num_cols[1]
        hover_labels = [str(x) if pd.notna(x) else "" for x in df[cat_cols[0]].tolist()] if cat_cols else None
        
        # Cap scatter points to 10,000 for browser DOM performance
        plot_df = df.head(10000)
        chart_res = {
            "type": "scatter",
            "title": f"{y_col.replace('_', ' ')} vs {x_col.replace('_', ' ')}",
            "x": plot_df[x_col].fillna(0).tolist(),
            "y": plot_df[y_col].fillna(0).tolist(),
            "x_label": x_col,
            "y_label": y_col
        }
        if hover_labels:
            chart_res["text"] = hover_labels[:len(plot_df)]
        return chart_res

    # Rule 2: Date column + numeric column -> Time Series Line Chart
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

    # Rule 3: Donut / Pie Chart - STRICT PART-TO-WHOLE INTEGRITY
    # Strictly PROHIBIT Pie/Donut charts on averages, means, ratings, or continuous measures
    # Pie charts are ONLY permitted on additive part-to-whole quantities (counts, frequencies) with 2 to 7 slices
    if len(cat_cols) == 1 and len(num_cols) == 1 and 2 <= len(df) <= 7:
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

        if is_count_or_sum and not is_average_or_rate:
            return {
                "type": "pie",
                "title": f"Distribution of {metric.replace('_', ' ')} by {cat_cols[0].replace('_', ' ')}",
                "labels": df[cat_cols[0]].astype(str).tolist(),
                "values": df[metric].fillna(0).tolist()
            }

    # Rule 4: Pivot / Multi-Numeric Table -> Grouped Bar Chart (barmode='group')
    # Detects true pivot tables (1 categorical row dimension + multiple numeric metric columns)
    # Strictly bounded to 2-30 categories and verified scale compatibility (< 50x)
    if cat_cols and len(num_cols) > 1 and 1 < len(df) <= 30:
        col_maxes = [df[c].dropna().abs().max() for c in num_cols if len(df[c].dropna()) > 0]
        col_maxes = [m for m in col_maxes if m > 0]
        scale_compatible = (max(col_maxes) / min(col_maxes) <= 50) if len(col_maxes) > 1 else True

        if scale_compatible:
            x_col = cat_cols[0]
            melted = df.melt(id_vars=[x_col], value_vars=num_cols, var_name="Metric", value_name="Value")
            series_list = []
            for n_col in num_cols:
                series_list.append({
                    "name": str(n_col).replace("_", " "),
                    "y": df[n_col].fillna(0).tolist()
                })
            return {
                "type": "grouped_bar",
                "barmode": "group",
                "title": f"Metrics Comparison across {x_col.replace('_', ' ')}",
                "x": df[x_col].astype(str).tolist(),
                "x_label": x_col,
                "series": series_list,
                "melted": melted.replace({np.nan: None}).to_dict(orient="records")
            }
        else:
            # If scale is incompatible (e.g. 289M streams vs count of 1), choose primary continuous metric
            primary_col = max(num_cols, key=lambda c: df[c].dropna().abs().max() if len(df[c].dropna()) > 0 else 0)
            x_col = cat_cols[0]
            plot_df = df.head(50)
            return {
                "type": "bar",
                "title": f"{primary_col.replace('_', ' ')} by {x_col.replace('_', ' ')}",
                "x": plot_df[x_col].astype(str).tolist(),
                "y": plot_df[primary_col].fillna(0).tolist(),
                "x_label": x_col,
                "y_label": primary_col
            }

    # Rule 5: 1 Category + 1 Numeric -> Single Bar Chart
    # Strictly requires at least one categorical column; never self-maps two numeric columns
    # Capped at 50 bars to prevent the "11,000-bar rendering wall"
    if cat_cols and len(num_cols) == 1:
        x_col = cat_cols[0]
        y_col = num_cols[0]
        plot_df = df.head(50)
        return {
            "type": "bar",
            "title": f"{y_col.replace('_', ' ')} by {x_col.replace('_', ' ')}",
            "x": plot_df[x_col].astype(str).tolist(),
            "y": plot_df[y_col].fillna(0).tolist(),
            "x_label": x_col,
            "y_label": y_col
        }

    # Rule 6: Fallback for 2+ Numeric Columns without explicit category -> Scatter Plot
    if len(num_cols) >= 2:
        x_col = num_cols[0]
        y_col = num_cols[1]
        plot_df = df.head(10000)
        hover_labels = [str(x) if pd.notna(x) else "" for x in df[cat_cols[0]].tolist()] if cat_cols else None
        chart_res = {
            "type": "scatter",
            "title": f"{y_col.replace('_', ' ')} vs {x_col.replace('_', ' ')}",
            "x": plot_df[x_col].fillna(0).tolist(),
            "y": plot_df[y_col].fillna(0).tolist(),
            "x_label": x_col,
            "y_label": y_col
        }
        if hover_labels:
            chart_res["text"] = hover_labels[:len(plot_df)]
        return chart_res

    return None

def sanitize_json_object(obj):
    """Replace float NaN, Infinity, -Infinity with None or clean numbers to satisfy strict JSON encoders."""
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    elif isinstance(obj, (np.floating, np.integer)):
        val = float(obj) if isinstance(obj, np.floating) else int(obj)
        if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
            return None
        return val
    elif isinstance(obj, dict):
        return {k: sanitize_json_object(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_json_object(v) for v in obj]
    return obj

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
            result = clean_dataframe_indices(result)

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

            chart_config = detect_chart_type(result, query=query)
            insights = generate_data_insights(query, result, chart_config, source_df=df)

            return sanitize_json_object({
                "success": True,
                "code": clean_code,
                "result_type": "dataframe",
                "total_rows": total_rows,
                "displayed_rows": len(records),
                "columns": list(result.columns),
                "data": records,
                "chart": chart_config,
                "insights": insights
            })

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
