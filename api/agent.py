import re
import json
import logging
import urllib.request
import urllib.error
import ssl
import pandas as pd
from typing import Dict, Any, Optional

def get_ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    except Exception:
        return ssl._create_unverified_context()

from utils.code_safety import strip_code_fences, is_code_safe, validate_python_syntax
from api.config import GEMINI_API_KEY, OPENAI_API_KEY, GROQ_API_KEY

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Data Analyst and Python/Pandas programmer.
The user has a pandas DataFrame loaded in memory as variable `df`.

Your goal is to answer the user's analytical question by writing safe, efficient Python code that computes the answer and assigns it to a variable named `result`.

Dataset Context:
- A DataFrame named `df` is already available in memory.
- You can use `df`, `pd`, and `np`.

CRITICAL RULES (VIOLATIONS WILL BE REJECTED):
1. STRICTLY FORBIDDEN: DO NOT write any `import` statements! (e.g. no `import matplotlib`, no `import seaborn`, no `import pandas`). Any import will cause security rejection.
2. STRICTLY FORBIDDEN: DO NOT use matplotlib, seaborn, or any plotting library (no `plt.`, no `fig, ax = plt.subplots()`).
   The web dashboard automatically renders interactive Plotly charts directly from your `result` DataFrame.
3. If the user asks for a chart, plot, boxplot, comparison, or distribution, DO NOT draw a chart in Python.
   Instead, COMPUTE the underlying summary data table (e.g. groupby, describe, or mean/median aggregations) and assign to `result`.
   Example for income comparison by attrition:
   result = df.groupby('Attrition')['MonthlyIncome'].agg(Mean='mean', Median='median', Std='std', Min='min', Max='max').reset_index()
4. Always return the answer in variable `result`.
5. If aggregating, always use `.reset_index()` so it produces clean tabular data.
6. Return ONLY bare python code, or code inside ```python ``` fences. Do not include conversational text.
"""

def sanitize_code(code: str) -> str:
    """
    Remove redundant harmless imports (like import pandas as pd, import numpy as np)
    since pd and np are already provided in the execution scope.
    """
    lines = code.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped in ["import pandas as pd", "import numpy as np", "import pandas", "import numpy"]:
            continue
        if stripped.startswith("from pandas import") or stripped.startswith("from numpy import"):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()

def is_ollama_available() -> bool:
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False

def query_ollama(prompt: str) -> str:
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
    """Directly route query to Google Gemini with automatic model resolution."""
    models = ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    last_err = None

    def call_model(model_name: str) -> Optional[str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048}
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=35, context=get_ssl_context()) as response:
            result_json = json.loads(response.read().decode("utf-8"))
            candidates = result_json.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
        return None

    # 1. Try preferred models
    for model in models:
        try:
            res = call_model(model)
            if res:
                logger.info(f"Successfully generated code using Gemini model: {model}")
                return res
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            if e.code == 429:
                last_err = "Gemini Free Tier rate limit reached (15 requests/min). Please wait 5-10 seconds before asking the next question."
            elif e.code == 403 or (e.code == 400 and "API_KEY_INVALID" in err_body):
                last_err = "Invalid Gemini API Key. Please verify your key from Google AI Studio (https://aistudio.google.com/app/apikey)."
            else:
                last_err = f"Gemini API error ({model}): HTTP {e.code} - {err_body}"
            logger.warning(last_err)
        except Exception as e:
            last_err = f"Gemini API error ({model}): {e}"
            logger.warning(last_err)

    # 2. Dynamic Discovery via ListModels if preferred models returned 404
    try:
        logger.info("Discovering available Gemini models via ListModels API...")
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        req_list = urllib.request.Request(list_url, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req_list, timeout=10, context=get_ssl_context()) as resp:
            m_data = json.loads(resp.read().decode("utf-8"))
            # Filter to prefer gemini models over gemma/text models
            all_supported = [
                m["name"].replace("models/", "")
                for m in m_data.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
            ]
            gemini_only = [m for m in all_supported if "gemini" in m.lower() and not "embedding" in m.lower()]
            available_models = gemini_only if gemini_only else all_supported
            for dyn_model in available_models:
                if dyn_model not in models:
                    try:
                        res = call_model(dyn_model)
                        if res:
                            logger.info(f"Successfully generated code with discovered model: {dyn_model}")
                            return res
                    except Exception:
                        continue
    except Exception as list_err:
        logger.warning(f"ListModels failed: {list_err}")

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
        with urllib.request.urlopen(req, timeout=35, context=get_ssl_context()) as response:
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
    api_key = custom_api_key.strip() or GEMINI_API_KEY or OPENAI_API_KEY or GROQ_API_KEY

    if not api_key:
        if is_ollama_available():
            logger.info("Routing query through local Ollama LLM...")
            prompt = f"DATASET COLUMNS:\n{list(df.columns)}\n\nSCHEMA:\n{schema}\n\nUSER QUESTION:\n{user_query}\n\nReturn Python code setting `result = ...`:"
            raw_code = query_ollama(prompt)
            clean_code = sanitize_code(strip_code_fences(raw_code))
            return {"code": clean_code, "provider": "ollama_local", "note": None}
        
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

    def call_llm(p: str):
        if api_key.startswith("gsk_"):
            return query_openai_compatible(p, api_key, base_url="https://api.groq.com/openai/v1", model="llama-3.3-70b-versatile"), "groq_llama33"
        elif api_key.startswith("sk-") and not api_key.startswith("sk-ant-"):
            return query_openai_compatible(p, api_key, base_url="https://api.openai.com/v1", model="gpt-4o-mini"), "openai_gpt4o"
        else:
            return query_gemini(p, api_key), "gemini_3.6_flash"

    # Attempt 1
    raw_code, provider = call_llm(prompt)
    clean_code = sanitize_code(strip_code_fences(raw_code))

    # Self-Correction Check: If code has syntax error, contains matplotlib, or violates safety
    is_valid_syntax, syntax_err = validate_python_syntax(clean_code)
    if not is_valid_syntax or not is_code_safe(clean_code) or "matplotlib" in clean_code or "plt." in clean_code or "seaborn" in clean_code:
        logger.warning(f"Initial code issue ({syntax_err or 'unsafe/matplotlib'}). Triggering self-correction retry...")
        logger.warning(f"Initial LLM code contained forbidden patterns: {clean_code[:100]}. Triggering self-correction retry...")
        retry_prompt = f"""{prompt}

CRITICAL FIX REQUIRED:
Your previous response had an issue ({syntax_err or 'forbidden imports/matplotlib'}):
```python
{clean_code}
```
Please provide complete, syntactically valid Python code with NO unclosed quotes and NO imports. Assign the final DataFrame to `result`.
REMEMBER:
1. STRICTLY FORBIDDEN: DO NOT write `import matplotlib` or use `plt.`. The web dashboard automatically creates the interactive charts from your `result` dataframe!
2. DO NOT import any modules.
3. Compute the underlying summary data table using ONLY `df`, `pd`, and `np`, and assign it to `result`.
   Example for distribution / boxplot comparison:
   result = df.groupby('Attrition')['MonthlyIncome'].agg(Mean='mean', Median='median', Std='std', Min='min', Max='max').reset_index()

Return ONLY executable Python code:"""
        try:
            raw_code, provider = call_llm(retry_prompt)
            clean_code = sanitize_code(strip_code_fences(raw_code))
        except Exception as retry_err:
            logger.error(f"Self-correction retry failed: {retry_err}")

    return {
        "code": clean_code,
        "provider": provider,
        "note": None
    }
