import os
import json
import logging
import urllib.request
import urllib.error
import pandas as pd
from typing import Dict, Any

from utils.code_safety import strip_code_fences, is_code_safe
from api.config import GEMINI_API_KEY, OPENAI_API_KEY

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Data Analyst and Python/Pandas programmer.
The user has a pandas DataFrame loaded in memory as variable `df`.

Your goal is to answer the user's analytical question by writing safe, efficient Python code that computes the answer and assigns it to a variable named `result`.

Dataset Context:
- A DataFrame named `df` is already available in memory.
- You can use `df`, `pd`, and `np`.
- Do NOT import any modules (import statement is strictly forbidden).
- Do NOT read or write files (open, os, sys, etc. are forbidden).
- Always return the answer in variable `result` (e.g. `result = df.groupby('Brand')['Revenue'].sum().reset_index()`).
- If aggregating, reset index (`.reset_index()`) so it produces clean columnar data.
- Return ONLY bare python code, or code inside ```python ``` fences. Do not include conversational filler.
"""

def generate_fallback_code(query: str, df: pd.DataFrame) -> str:
    """
    Intelligent heuristic fallback to generate pandas code when no LLM API key is provided.
    Provides immediate runnable experience out-of-the-box.
    """
    q = query.lower()

    # Brand revenue
    if "brand" in q and ("revenue" in q or "sales" in q):
        n = 5 if "5" in q else (10 if "10" in q else 10)
        return f"result = df.groupby('Brand')['Revenue'].sum().reset_index().sort_values(by='Revenue', ascending=False).head({n})"

    # State revenue
    if "state" in q:
        return "result = df.groupby('State')['Revenue'].sum().reset_index().sort_values(by='Revenue', ascending=False)"

    # Store profit/performance
    if "store" in q and ("profit" in q or "margin" in q):
        return "result = df.groupby('store')[['Revenue', 'Profit']].sum().assign(Profit_Margin_Pct=lambda x: (x['Profit']/x['Revenue'])*100).reset_index().sort_values(by='Profit', ascending=False)"

    if "store" in q:
        return "result = df.groupby('store')['Revenue'].sum().reset_index().sort_values(by='Revenue', ascending=False)"

    # City sales
    if "city" in q:
        return "result = df.groupby('City')['Revenue'].sum().reset_index().sort_values(by='Revenue', ascending=False)"

    # Product ratings / top products
    if "rating" in q or "rated" in q:
        return "result = df.groupby('Product Title')['Customer_Rating'].mean().reset_index().sort_values(by='Customer_Rating', ascending=False).head(10)"

    if "product" in q or "item" in q:
        return "result = df.groupby('Product Title')[['Units_Sold', 'Revenue']].sum().reset_index().sort_values(by='Revenue', ascending=False).head(10)"

    # Monthly / Date trend
    if "trend" in q or "month" in q or "time" in q or "date" in q:
        if 'Date' in df.columns:
            return "result = df.assign(Month=pd.to_datetime(df['Date']).dt.to_period('M').astype(str)).groupby('Month')[['Revenue', 'Profit']].sum().reset_index()"

    # Totals / Summary KPI
    if "total" in q or "kpi" in q or "summary" in q or "overall" in q:
        metrics = []
        if 'Revenue' in df.columns:
            metrics.append("'Total_Revenue': [df['Revenue'].sum()]")
        if 'Profit' in df.columns:
            metrics.append("'Total_Profit': [df['Profit'].sum()]")
        if 'Units_Sold' in df.columns:
            metrics.append("'Total_Units_Sold': [df['Units_Sold'].sum()]")
        if metrics:
            return f"result = pd.DataFrame({{{', '.join(metrics)}}})"

    # District
    if "district" in q:
        return "result = df.groupby('District')[['Revenue', 'Profit']].sum().reset_index().sort_values(by='Revenue', ascending=False)"

    # Default fallback: show head summary
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    if numeric_cols:
        first_num = numeric_cols[0]
        cat_cols = [c for c in df.columns if c not in numeric_cols]
        first_cat = cat_cols[0] if cat_cols else df.columns[0]
        return f"result = df.groupby('{first_cat}')['{first_num}'].sum().reset_index().sort_values(by='{first_num}', ascending=False).head(10)"

    return "result = df.head(10)"

def query_gemini(prompt: str, api_key: str) -> str:
    """Call Google Gemini 2.0 Flash / 1.5 Flash using direct HTTPS request."""
    # Try gemini-2.0-flash first, fallback to 1.5-flash
    models = ["gemini-2.0-flash", "gemini-1.5-flash"]
    last_err = None

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1000
            }
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
            logger.warning(f"Gemini {model} returned HTTP {e.code}: {e.read().decode('utf-8')}")
        except Exception as e:
            last_err = e
            logger.warning(f"Gemini {model} failed: {e}")

    raise RuntimeError(f"Gemini API request failed: {last_err}")

def query_openai(prompt: str, api_key: str) -> str:
    """Call OpenAI API using direct HTTPS request."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 800
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    with urllib.request.urlopen(req, timeout=12) as response:
        result_json = json.loads(response.read().decode("utf-8"))
        return result_json["choices"][0]["message"]["content"].strip()

def generate_pandas_code(
    user_query: str,
    df: pd.DataFrame,
    schema: str,
    summary: str,
    data_dictionary: str,
    custom_api_key: str = ""
) -> Dict[str, Any]:
    """
    Generate Python pandas code from user natural language query.
    Incorporate schema, summary, and data dictionary into LLM prompt.
    """
    api_key = custom_api_key.strip() or GEMINI_API_KEY or OPENAI_API_KEY
    is_gemini = bool(custom_api_key.strip() or GEMINI_API_KEY)
    provider = "gemini" if is_gemini and api_key else ("openai" if OPENAI_API_KEY else "offline_heuristic")

    # Construct prompt
    prompt = f"""{SYSTEM_PROMPT}

DATASET SCHEMA:
{schema}

DATA DICTIONARY / BUSINESS CONTEXT:
{data_dictionary}

SAMPLE STATISTICAL SUMMARY:
{summary[:1200]}

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
            if is_gemini:
                raw_code = query_gemini(prompt, api_key)
            else:
                raw_code = query_openai(prompt, api_key)
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
