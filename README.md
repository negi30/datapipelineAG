# DatapipelineA1: Agentic Data Analysis Pipeline 🚀

## 📖 Overview
**DatapipelineA1** is an intelligent, locally-executed data analysis application that transforms natural language questions into deterministic Python code. 

Rather than sending raw, potentially sensitive datasets to an external Large Language Model (LLM), DatapipelineA1 utilizes an **Agentic Data Pipeline**. It automatically extracts the structural schema and statistical metadata of an uploaded CSV, passes only that lightweight context to the LLM (OpenAI GPT-4o) to generate strict pandas or Plotly code, and then securely executes that code locally. 

This architecture ensures **100% mathematical accuracy**, strict **data privacy**, and massive **token efficiency**—solving the core limitations of standard LLM data-chat interfaces.

## ✨ Key Features
- **Privacy-First Processing:** Raw data never leaves your local machine; only the dataset schema and summary statistics are sent to the LLM to generate the processing logic.
- **Deterministic Accuracy:** Bypasses LLM hallucinations in mathematics by forcing the AI to act exclusively as a code generator, while the local Python environment handles the actual calculations.
- **Dynamic Visualizations:** Automatically writes and safely executes Plotly code to render interactive charts and graphs based on natural language prompts.
- **Two-Step Query Verification:** Optimizes API costs by first returning a "Result Count" preview, allowing users to verify query accuracy before generating a full textual synthesis.
- **Automated Schema Extraction:** Instantly profiles uploaded CSVs to generate data dictionaries, column types, and statistical boundaries.

## 💡 Example Use Cases
* **Financial Time-Series Analysis:** Extract and process specific fields—such as tracking premiums from public financial disclosures (e.g., nl4 filings)—across thousands of rows to gain historical insights without exposing the raw corporate data to external servers.
* **Sports Analytics & Machine Learning Prep:** Query comprehensive NBA basketball or Premier League soccer statistics to identify player performance metrics, aggregate seasonal data, or generate heatmaps to use as features for predictive machine learning models.
* **HR & Attrition Data:** Analyze employee turnover rates across departments to isolate retention bottlenecks.

## 🧰 Tech Stack
- **Backend Orchestration:** FastAPI, Uvicorn, Python `exec()` sandboxing
- **AI / LLM Framework:** LangChain, OpenAI API (GPT-4o)
- **Data Processing & Viz:** Pandas, Plotly (Express & Graph Objects)
- **Frontend UI:** Streamlit

## 📦 Installation & Setup

### Prerequisites
- Python 3.10 or higher
- An active OpenAI API Key

### 1. Clone the Repository
```bash
git clone [https://github.com/](https://github.com/)[Your-GitHub-Username]/datapipelinea1.git
cd datapipelinea1