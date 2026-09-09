# 📊 DataChat AI Agent - 10MB Dataset Analytics & Runner

A production-ready, full-stack AI Data Analysis Application built for tabular datasets (CSV & Parquet up to **10MB**). It enables natural language questions, translates them into verified Pandas code, safely executes the code in a sandboxed environment, and delivers interactive tables and Plotly visualizations.

Engineered with dual runtime support:
- **Local Runnable**: Launch with a single command (`python app.py`) or use the terminal CLI (`python run_cli.py`).
- **Vercel Serverless Ready**: Configured with `vercel.json` and optimized dependencies to deploy effortlessly within Vercel's serverless size and memory limits.

---

## 🚀 Key Functionalities & Features

### 1. Schema Extractor (`utils/schema_extractor.py`)
- Automatically extracts data types, summary statistics (mean, std) for numeric columns, and unique values for categorical, boolean, and date columns.
- **Smart Metadata Exclusion (`to_ignore`)**: Automatically filters out high-cardinality metadata columns (`store`, `Product ID`, `Product Title`, `Brand`, `Unit`, `Quantity Per Case`, `State`, `City`, `District`) from unique value lists to prevent token bloat while keeping them available for aggregations and filtering in queries.

### 2. Statistical Summary Generator (`utils/summary_generator.py`)
- Computes comprehensive dataset statistics using pandas `df.describe(include='all')`.
- Integrated with `rich.console` for beautiful terminal logging and debugging.

### 3. Business Data Dictionary (`data/data_dictionary.txt`)
- Extracted via `extract_data_dictionary(df)`. Provides business context and field definitions so the AI agent understands domain terms (e.g., mapping "margin" to `(Revenue - Cost) / Revenue`).

### 4. Code Safety & Denylist Sandbox (`utils/code_safety.py`)
- **Denylist Validation (`is_code_safe`)**: Rejects any code containing dangerous system calls or escape hatches (`import`, `open(`, `exec(`, `eval(`, `os.`, `sys.`, `subprocess`, `__`, etc.).
- **Code Fence Stripper (`strip_code_fences`)**: Cleans off markdown blocks (` ```python ... ``` `).
- **AST Syntax Checking (`validate_python_syntax`)**: Verifies code validity before execution.

### 5. Safe Execution Engine (`api/execution_engine.py`)
- Executes generated Python/Pandas code in a restricted scope `{"df": df, "pd": pd, "np": np}` with strict execution timeouts.
- Captures scalar metrics, lists, dicts, or DataFrames.
- **Automatic Chart Detection**: Ingests result DataFrames and auto-generates Plotly chart specifications:
  - **Bar Charts**: 1 categorical column + numeric metrics.
  - **Time Series Line Charts**: Date columns + numeric metrics.
  - **Donut / Pie Charts**: Low-cardinality category distributions.
  - **Scatter Plots**: Multi-variable numeric relationships.
- **Data Export**: One-click CSV export of query results.

### 6. Memory Optimization & 10MB Ingestion (`api/data_loader.py`)
- Built specifically to prevent memory inflation on serverless environments.
- Downcasts float64 to float32 and int64 to int32.
- Converts low-cardinality strings to memory-efficient pandas `category` dtype, slashing memory footprint by 75-80%.
- Supports direct CSV & Parquet uploads up to 10MB, plus remote URL loading.

### 7. Dual AI Generation Engine (`api/agent.py`)
- **Cloud LLMs**: Native support for Google Gemini (`gemini-2.0-flash`, `gemini-1.5-flash`) and OpenAI (`gpt-4o-mini`).
- **Built-in Offline Heuristic Analyzer**: Works out-of-the-box with zero configuration or API key. Handles common analytical queries (top brands, state rankings, store margins, monthly trends, ratings) immediately.

---

## 📁 Project Structure

```
data-agent/
├── api/
│   ├── index.py              # FastAPI server & Vercel serverless entrypoint
│   ├── agent.py              # AI Agent (Gemini / OpenAI / Offline Heuristics)
│   ├── execution_engine.py   # Sandboxed code execution & Plotly inference
│   ├── data_loader.py        # Dataset manager, memory downcasting & 10MB loader
│   └── config.py             # App configuration & environment variables
├── utils/
│   ├── __init__.py
│   ├── summary_generator.py  # User's summary generator with rich console
│   ├── schema_extractor.py   # User's schema extractor with ignored columns
│   └── code_safety.py        # User's code safety validator & fence stripper
├── public/
│   ├── index.html            # High-polish interactive web dashboard
│   ├── app.js                # Frontend state, charts, and query handling
│   └── style.css             # Modern styling & theme overrides
├── data/
│   ├── sample_retail_data.csv# Bundled sample retail dataset
│   └── data_dictionary.txt   # Field business definitions
├── app.py                    # Local web runner (auto-opens browser)
├── run_cli.py                # Terminal interactive REPL
├── requirements.txt          # Lightweight dependencies for Vercel (< 500MB lambda)
├── vercel.json               # Vercel deployment configuration
├── .env.example              # Environment variables template
└── README.md                 # Complete documentation
```

---

## 🏃 Running Locally

### 1. Prerequisites
- Python 3.10, 3.11, or 3.12 installed.

### 2. Installation
Clone or navigate to the project directory:
```bash
cd /Users/neilnegi/.gemini/antigravity/scratch/data-agent
```

Install dependencies:
```bash
pip install -r requirements.txt
```

### 3. Launch Web Application
Run the launcher:
```bash
python app.py
```
This automatically starts the server and opens your browser at:
👉 **`http://localhost:8000`**

### 4. Or Run via Terminal CLI
For terminal lovers, an interactive REPL with `rich` console styling is available:
```bash
python run_cli.py
```
Commands in CLI:
- Type any question (e.g. `top 5 brands by revenue`, `monthly sales trend`)
- Type `schema` to view the schema table
- Type `summary` to view statistical properties
- Type `dict` to view the business definitions
- Type `exit` to quit

---

## ☁️ Deploying to Vercel Online

This project is pre-configured for Vercel via `@vercel/python` and `vercel.json`.

### Option A: Deploy via Vercel CLI (Fastest)

1. Install the Vercel CLI if you haven't already:
```bash
npm install -g vercel
```

2. Log in to Vercel:
```bash
vercel login
```

3. Deploy from the project root:
```bash
vercel --prod
```

### Option B: Deploy via GitHub / Vercel Web Dashboard

1. Push this directory to a GitHub repository:
```bash
git init
git add .
git commit -m "Initial commit of DataChat AI Agent"
git branch -M main
git remote add origin https://github.com/your-username/your-repo.git
git push -u origin main
```

2. Open your [Vercel Dashboard](https://vercel.com/dashboard) and click **"Add New Project"**.
3. Import your GitHub repository.
4. **Environment Variables** (Optional, configure under Project Settings -> Environment Variables):
   - `GEMINI_API_KEY`: Your Google Gemini API Key (e.g., from Google AI Studio).
   - `OPENAI_API_KEY`: (Optional) Your OpenAI API Key.
   - `MAX_DATASET_MB`: `10`
5. Click **Deploy**. Vercel will automatically build the Python serverless function and static frontend!

---

## 🔌 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Healthcheck and active dataset status |
| `GET` | `/api/info` | Returns dataset row count, columns, schema, summary, and data dictionary |
| `POST` | `/api/query` | Submits natural language question -> returns generated code, safety check, data records, and chart configuration |
| `POST` | `/api/upload` | Uploads a custom CSV or Parquet file (up to 10MB) |
| `POST` | `/api/load-url` | Downloads and activates a dataset from an external URL |
| `POST` | `/api/reset` | Resets the active dataset to the default retail sample |

---

## 🛡️ Security Note
The execution engine enforces a strict security policy using `utils/code_safety.py` and AST syntax tree verification. All executions are scoped to safe in-memory operations on the pandas DataFrame, preventing unauthorized system calls, network access, or shell escapes.
