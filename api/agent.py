import re
import json
import logging
import urllib.request
import urllib.error
import pandas as pd
from typing import Dict, Any, List, Optional

from utils.code_safety import strip_code_fences
from api.config import GEMINI_API_KEY, OPENAI_API_KEY

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Data Analyst and Python/Pandas programmer.
The user has a pandas DataFrame loaded in memory as variable `df`.

Your goal is to answer the user's analytical question by writing safe, efficient Python code that computes the answer and assigns it to a variable named `result`.

Dataset Context:
- A DataFrame named `df` is already available in memory.
- You can use `df`, `pd`, and `np`.
- Do NOT import any modules.
- Do NOT read or write files.
- Always assign output to variable `result`.
- If aggregating, use `.reset_index()`.
- Return ONLY bare python code.
"""

SYNONYMS = {
    "attrition": ["attrition", "turnover", "churn", "leaving", "left", "quit"],
    "income": ["salary", "income", "compensation", "earnings", "pay", "wage", ""],
    "tenure": ["yearsatcompany", "years at company", "tenure", "totalworkingyears", "experience"],
    "satisfaction": ["satisfaction", "happiness", "morale"],
    "rating": ["rating", "score", "performance"],
    "revenue": ["revenue", "sales", "proceeds"],
    "profit": ["profit", "margin"],
    "role": ["jobrole", "role", "title", "position"],
    "dept": ["department", "division", "team"],
    "status": ["maritalstatus", "marital", "status"]
}

def clean_col(name: str) -> str:
    # Convert camelCase / PascalCase / snake_case to lowercase space-separated
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', str(name))
    return s.lower().replace('_', ' ').replace('-', ' ').strip()

def find_col_in_query(query: str, df: pd.DataFrame, prefer_numeric: bool = False, prefer_cat: bool = False) -> Optional[str]:
    q = query.lower()
    cols = list(df.columns)
    
    # Sort columns by length descending to match longest column names first
    sorted_cols = sorted(cols, key=lambda c: len(str(c)), reverse=True)
    
    # 1. Exact match on normalized column name
    for c in sorted_cols:
        norm = clean_col(c)
        if norm in q or norm.replace(" ", "") in q.replace(" ", ""):
            if prefer_numeric and not pd.api.types.is_numeric_dtype(df[c]):
                continue
            if prefer_cat and pd.api.types.is_numeric_dtype(df[c]):
                continue
            return c
            
    # 2. Check synonyms
    for standard, syns in SYNONYMS.items():
        if any(syn in q for syn in syns):
            for c in sorted_cols:
                norm = clean_col(c)
                if any(syn in norm or norm in syn for syn in syns):
                    if prefer_numeric and not pd.api.types.is_numeric_dtype(df[c]):
                        continue
                    if prefer_cat and pd.api.types.is_numeric_dtype(df[c]):
                        continue
                    return c
                    
    return None

def generate_fallback_code(query: str, df: pd.DataFrame) -> str:
    """
    Intelligent heuristic fallback to generate pandas code for ANY dataset
    when no LLM API key is provided.
    """
    q = query.lower()
    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    cat_cols = [c for c in df.columns if c not in num_cols]

    # Detect binary column (e.g. Attrition, Churn, In_Stock)
    binary_col = None
    for c in df.columns:
        uniques = [str(x).lower().strip() for x in df[c].dropna().unique() if str(x) != 'nan']
        if set(uniques) in [{'yes', 'no'}, {'y', 'n'}, {'true', 'false'}, {'0', '1'}, {'1', '0'}]:
            binary_col = c
            break

    # Intent 1: Attrition / Churn / Binary Rate ("", "percentage", "turnover", "affect turnover")
    is_rate_query = any(k in q for k in ["", "percentage", "%", "turnover", "attrition", "churn", "proportion"])
    is_affect_query = any(k in q for k in ["affect", "impact", "relationship", "vs", "by", "how does"])

    if binary_col and (is_rate_query or binary_col.lower() in q or "turnover" in q or "churn" in q):
        group_col = None
        if not any(w in q for w in ["overall", "total", "across all", "general"]):
            remaining_q = q.replace(clean_col(binary_col), "").replace("turnover", "").replace("attrition", "").replace("churn", "").replace("rate", "")
            group_col = find_col_in_query(remaining_q, df)

        if group_col and group_col != binary_col:
            return (
                f"is_positive = df['{binary_col}'].astype(str).str.lower().isin(['yes', 'y', 'true', '1'])\n"
                f"result = df.assign({binary_col}_Flag=is_positive).groupby('{group_col}')['{binary_col}_Flag']"
                f".agg(Total_Count='count', Positive_Count='sum', Rate_Pct=lambda x: round(x.mean() * 100, 2)).reset_index()"
            )
        else:
            # Overall binary rate
            return (
                f"counts = df['{binary_col}'].value_counts().reset_index()\n"
                f"counts.columns = ['Status', 'Count']\n"
                f"counts['Percentage'] = (counts['Count'] / len(df) * 100).round(2)\n"
                f"result = counts"
            )

    # Intent 2: "How does X affect Y" or "Y by X"
    if is_affect_query:
        target_num = find_col_in_query(q, df, prefer_numeric=True)
        target_cat = find_col_in_query(q, df, prefer_cat=True)
        if target_num and target_cat and target_num != target_cat:
            op = "sum" if "total" in q else "mean"
            return f"result = df.groupby('{target_cat}')['{target_num}'].{op}().round(2).reset_index().sort_values(by='{target_num}', ascending=False)"

    # Intent 3: Average / Mean / Total / Distribution
    metric_col = find_col_in_query(q, df, prefer_numeric=True)
    group_col = find_col_in_query(q, df, prefer_cat=True)

    if metric_col and group_col and metric_col != group_col:
        op = "sum" if any(w in q for w in ["total", "sum"]) else "mean"
        return f"result = df.groupby('{group_col}')['{metric_col}'].{op}().round(2).reset_index().sort_values(by='{metric_col}', ascending=False).head(15)"

    # Intent 4: Single categorical distribution / count
    single_cat = find_col_in_query(q, df, prefer_cat=True)
    if single_cat:
        return f"result = df['{single_cat}'].value_counts().reset_index().rename(columns={{'index': '{single_cat}', '{single_cat}': 'Count'}}).head(15)"

    # Intent 5: Top / Highest / Lowest single metric
    if metric_col:
        ascending = "true" if any(w in q for w in ["lowest", "least", "bottom", "min"]) else "False"
        first_cat = cat_cols[0] if cat_cols else df.columns[0]
        return f"result = df.groupby('{first_cat}')['{metric_col}'].mean().round(2).reset_index().sort_values(by='{metric_col}', ascending={ascending}).head(10)"

    # Intent 6: General summary KPI
    if any(k in q for k in ["summary", "overview", "total", "kpi"]):
        if num_cols:
            selected_num = num_cols[:4]
            aggs = {c: ["mean", "sum"] for c in selected_num}
            return f"result = df[{selected_num}].describe().T[['mean', 'std', 'min', 'max']].round(2).reset_index()"

    # Default fallback: safe head or first group
    if cat_cols and num_cols:
        return f"result = df.groupby('{cat_cols[0]}')['{num_cols[0]}'].mean().round(2).reset_index().sort_values(by='{num_cols[0]}', ascending=False).head(10)"

    return "result = df.head(10)"

def query_gemini(prompt: str, api_key: str) -> str:
    models = ["gemini-2.0-flash", "gemini-1.5-flash"]
    last_err = None

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1000}
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                result_json = json.loads(response.read().decode("utf-8"))
                candidates = result_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
        except urllib.error.HTTPError as e:
            last_err = e
            logger.warning(f"Gemini {model} returned HTTP {e.code}")
        except Exception as e:
            last_err = e
            logger.warning(f"Gemini {model} failed: {e}")

    raise RuntimeError(f"Gemini API request failed: {last_err}")

def generate_pandas_code(
    user_query: str,
    df: pd.DataFrame,
    schema: str,
    summary: str,
    data_dictionary: str,
    custom_api_key: str = ""
) -> Dict[str, Any]:
    api_key = custom_api_key.strip() or GEMINI_API_KEY or OPENAI_API_KEY
    is_gemini = bool(custom_api_key.strip() or GEMINI_API_KEY)
    provider = "gemini" if is_gemini and api_key else ("offline_heuristic")

    prompt = f"""{SYSTEM_PROMPT}

DATASET SCHEMA:
{schema}

ALL AVAILABLE COLUMNS IN `df`:
{list(df.columns)}

USER QUESTION:
{user_query}

Write the Python code to answer the user question and assign to `result`.
Code:"""

    raw_code = ""
    error_note = None

    if api_key:
        try:
            raw_code = query_gemini(prompt, api_key)
        except Exception as e:
            logger.error(f"LLM API call failed: {e}. Falling back to heuristic engine.")
            error_note = f"LLM API error: {str(e)[:150]}. Used offline heuristic engine."
            raw_code = generate_fallback_code(user_query, df)
            provider = "offline_fallback"
    else:
        raw_code = generate_fallback_code(user_query, df)
        provider = "offline_heuristic"

    clean_code = strip_code_fences(raw_code)

    return {
        "code": clean_code,
        "provider": provider,
        "note": error_note
    }
