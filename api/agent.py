import re
import json
import logging
import urllib.request
import urllib.error
import pandas as pd
from typing import Dict, Any, Optional

from utils.code_safety import strip_code_fences
from api.config import GEMINI_API_KEY, OPENAI_API_KEY, GROQ_API_KEY

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Data Analyst and Python/Pandas programmer.
The user has a pandas DataFrame loaded in memory as variable `df`.

Your goal is to answer the user's analytical question by writing safe, efficient Python code that computes the answer and assigns it to a variable named `result`.

Dataset Context:
- A DataFrame named `df` is already available in memory.
- You can use `df`, `pd`, and `np`.
- Do NOT import any modules (import statement is strictly forbidden).
- Do NOT read or write files (open, os, sys, etc. are forbidden).
- Always return the answer in variable `result` (e.g. `result = df.groupby('Department')['MonthlyIncome'].mean().reset_index()`).
- If aggregating, always use `.reset_index()` so it produces clean columnar data.
- Return ONLY bare python code, or code inside ```python ``` fences. Do not include conversational text or explanations.
"""

def is_ollama_available() -> bool:
    """Check if a local Ollama server is running without requiring an API key."""
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False

def query_ollama(prompt: str) -> str:
    """Call local Ollama instance."""
    # Find installed model
    req = urllib.request.Request("http://localhost:11434/api/tags")
    with urllib.request.urlopen(req, timeout=2) as resp:
        tags = json.loads(resp.read().decode("utf-8"))
        models = [m["name"] for m in tags.get("models", [])]
        model = models[0] if models else "llama3"

    payload = {
        "model": model,
        "prompt": f"{SYSTEM_PROMPT}\n\n{prompt}",
        "stream": False
    }
    data = json.dumps(payload).encode("utf-8")
    req_gen = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req_gen, timeout=30) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return res.get("response", "").strip()

def query_gemini(prompt: str, api_key: str) -> str:
    """Directly route query to Google Gemini (Gemini 2.0 Flash / 1.5 Flash)."""
    models = ["gemini-2.0-flash", "gemini-1.5-flash"]
    last_err = None

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1200
            }
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                result_json = json.loads(response.read().decode("utf-8"))
                candidates = result_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            last_err = f"Gemini API error ({model}): HTTP {e.code} - {err_body}"
            logger.warning(last_err)
        except Exception as e:
            last_err = f"Gemini API error ({model}): {e}"
            logger.warning(last_err)

    raise RuntimeError(last_err or "Gemini API request failed.")

def query_openai_compatible(prompt: str, api_key: str, base_url: str = "https://api.openai.com/v1", model: str = "gpt-4o-mini") -> str:
    """Directly route query to OpenAI or Groq."""
    url = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 1000
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            result_json = json.loads(response.read().decode("utf-8"))
            return result_json["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI/Groq API error: HTTP {e.code} - {err_body}")

def generate_pandas_code(
    user_query: str,
    df: pd.DataFrame,
    schema: str,
    summary: str,
    data_dictionary: str,
    custom_api_key: str = ""
) -> Dict[str, Any]:
    """
    STRICT LLM ROUTER:
    Guarantees that EVERY query is routed through a real Large Language Model
    (Google Gemini 2.0 Flash, OpenAI, Groq, or Local Ollama).
    """
    api_key = custom_api_key.strip() or GEMINI_API_KEY or OPENAI_API_KEY or GROQ_API_KEY

    # If no API key, check if local Ollama is running
    if not api_key:
        if is_ollama_available():
            logger.info("Routing query through local Ollama LLM...")
            prompt = f"DATASET COLUMNS:\n{list(df.columns)}\n\nSCHEMA:\n{schema}\n\nUSER QUESTION:\n{user_query}\n\nReturn Python code setting `result = ...`:"
            raw_code = query_ollama(prompt)
            clean_code = strip_code_fences(raw_code)
            return {"code": clean_code, "provider": "ollama_local", "note": None}
        
        # If neither is available, RAISE EXPLICIT ERROR so user knows an LLM key is needed
        raise ValueError(
            "NO_LLM_KEY: All queries must be routed through an LLM. Please provide a Google Gemini API Key "
            "(free from Google AI Studio: https://aistudio.google.com/app/apikey) or an OpenAI/Groq API key "
            "by clicking the 'API Key' button in the top right, or set GEMINI_API_KEY in your .env file."
        )

    # Prepare LLM Context
    prompt = f"""{SYSTEM_PROMPT}

DATASET SCHEMA & COLUMN TYPES:
{schema}

BUSINESS CONTEXT / DATA DICTIONARY:
{data_dictionary[:1000] if data_dictionary else 'None'}

DATASET SAMPLE SUMMARY:
{summary[:1200] if summary else 'None'}

ALL AVAILABLE COLUMNS IN `df`:
{list(df.columns)}

USER QUESTION:
{user_query}

Write the Python code to compute the exact answer to the user question and assign it to `result`.
Return ONLY executable Python code:"""

    # Route according to key type
    if api_key.startswith("gsk_"):
        logger.info("Routing query to Groq LLM (llama-3.3-70b-versatile)...")
        raw_code = query_openai_compatible(prompt, api_key, base_url="https://api.groq.com/openai/v1", model="llama-3.3-70b-versatile")
        provider = "groq_llama33"
    elif api_key.startswith("sk-") and not api_key.startswith("sk-ant-"):
        logger.info("Routing query to OpenAI LLM (gpt-4o-mini)...")
        raw_code = query_openai_compatible(prompt, api_key, base_url="https://api.openai.com/v1", model="gpt-4o-mini")
        provider = "openai_gpt4o"
    else:
        logger.info("Routing query to Google Gemini 2.0 Flash LLM...")
        raw_code = query_gemini(prompt, api_key)
        provider = "gemini_2.0_flash"

    clean_code = strip_code_fences(raw_code)

    return {
        "code": clean_code,
        "provider": provider,
        "note": None
    }
