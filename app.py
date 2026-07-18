from dotenv import load_dotenv
load_dotenv()  # must run before any agent imports read OPENAI_API_KEY

import uvicorn
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from utils.data_loader import load_csv
from utils.schema_extractor import extract_schema, extract_data_dictionary
from utils.summary_generator import generate_summary
from agents.query_generator import generate_pandas_query
from agents.response_generator import generate_final_response
from agents.visualizer import generate_plotly_code, get_plotly_json
from utils.code_safety import strip_code_fences, is_code_safe

import os
import logging
from rich.console import Console
import pandas as pd

console = Console()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Enable CORS for all origins (adjust as needed for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = "data"

# Ensure the data directory exists
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)


def build_context(df):
    """
    Runs schema/data-dictionary/summary extraction and surfaces failures
    (e.g. a missing data_dictionary.txt) as a clear error instead of an
    unhandled 500. Returns (schema, data_dictionary, summary, error_response).
    error_response is None on success, or a JSONResponse to return as-is.
    """
    try:
        schema = extract_schema(df)
        data_dictionary = extract_data_dictionary(df)
        summary = generate_summary(df)
        return schema, data_dictionary, summary, None
    except FileNotFoundError as e:
        logger.error(f"Missing required file while building context: {e}")
        return None, None, None, JSONResponse(
            content={"error": f"Missing required file: {e.filename}. "
                               "Make sure data_dictionary.txt exists in the project root."},
            status_code=400,
        )
    except Exception as e:
        logger.error(f"Failed to build context: {e}")
        return None, None, None, JSONResponse(
            content={"error": f"Failed to analyze the dataset: {e}"},
            status_code=400,
        )


@app.post("/upload_csv/")
async def upload_csv(file: UploadFile = File(...)):
    """
    Endpoint to upload a CSV file.
    """
    safe_filename = os.path.basename(file.filename)  # avoid path traversal
    file_location = f"{DATA_DIR}/{safe_filename}"
    with open(file_location, "wb+") as file_object:
        file_object.write(await file.read())
    logger.info(f"File '{safe_filename}' saved at '{file_location}'")
    return {"info": f"file '{safe_filename}' saved at '{file_location}'", "filename": safe_filename}


@app.post("/ask_question/")
async def ask_question(
    question: str = Form(...),
    filename: str = Form(...),
    confirm: bool = Form(False)
):
    """
    Endpoint to ask a question about the uploaded CSV data.
    If 'confirm' is False, it returns the count of query results.
    If 'confirm' is True, it returns the final response.
    """
    logger.info(f"Received question: '{question}' for file: '{filename}', confirm={confirm}")

    # Load Data
    df = load_csv(f"{DATA_DIR}/{filename}")
    if df is None:
        logger.error("Failed to load dataframe.")
        return JSONResponse(
            content={"error": "Failed to load the dataframe."},
            status_code=400,
        )

    # Extract Schema, Data Dictionary, and Summary
    schema, data_dictionary, summary, error_response = build_context(df)
    if error_response is not None:
        return error_response

    if not confirm:
        # Generate Pandas Query
        pandas_query = generate_pandas_query(question, schema, data_dictionary)

        if not pandas_query:
            logger.error("Failed to generate a valid pandas query.")
            return JSONResponse(
                content={"error": "Failed to generate a valid pandas query."},
                status_code=400,
            )

        pandas_query = strip_code_fences(pandas_query)
        if not is_code_safe(pandas_query):
            logger.error(f"Generated code failed safety check: {pandas_query}")
            return JSONResponse(
                content={"error": "Generated query failed a safety check."},
                status_code=400,
            )

        # Execute Query
        _vars = {"df": df, 'query_result': None, 'pd': pd}
        try:
            exec(pandas_query, _vars)
            query_result = _vars.get('query_result', None)
            if query_result is None:
                raise ValueError("The generated query did not assign a value to 'query_result'.")
            
            # Determine the count based on the type of query_result
            if isinstance(query_result, (pd.DataFrame, list, dict, set, tuple)):
                count = len(query_result)
            else:
                count = 1  # For scalar results
            logger.info(f"Number of query results: {count}")
        except Exception as e:
            logger.error(f"Failed to execute query: {e}")
            return JSONResponse(
                content={"error": f"Failed to execute query: {e}"},
                status_code=400,
            )

        return {"count": count}
    else:
        # Generate Pandas Query
        pandas_query = generate_pandas_query(question, schema, data_dictionary)

        if not pandas_query:
            logger.error("Failed to generate a valid pandas query.")
            return JSONResponse(
                content={"error": "Failed to generate a valid pandas query."},
                status_code=400,
            )

        pandas_query = strip_code_fences(pandas_query)
        if not is_code_safe(pandas_query):
            logger.error(f"Generated code failed safety check: {pandas_query}")
            return JSONResponse(
                content={"error": "Generated query failed a safety check."},
                status_code=400,
            )

        # Execute Query
        _vars = {"df": df, 'query_result': None, 'pd': pd}
        try:
            exec(pandas_query, _vars)
            query_result = _vars.get('query_result', None)
            if query_result is None:
                raise ValueError("The generated query did not assign a value to 'query_result'.")
            logger.info("Successfully executed pandas query.")
        except Exception as e:
            logger.error(f"Failed to execute query: {e}")
            return JSONResponse(
                content={"error": f"Failed to execute query: {e}"},
                status_code=400,
            )

        # Generate Final Response
        final_response = generate_final_response(question, query_result, summary)

        logger.info(f"Generated response: {final_response}")

        return {"response": final_response}


@app.post("/visualize/")
async def visualize(
    question: str = Form(...), 
    filename: str = Form(...), 
    confirm: bool = Form(False)
):
    """
    Endpoint to generate a Plotly visualization based on the user's question.
    If 'confirm' is False, it returns the count of the data to be visualized.
    If 'confirm' is True, it returns the final Plotly JSON.
    """
    logger.info(f"Received visualization request: '{question}' for file: '{filename}', confirm={confirm}")

    # Load Data
    df = load_csv(f"{DATA_DIR}/{filename}")

    if df is None:
        logger.error("Failed to load dataframe.")
        return JSONResponse(
            content={"error": "Failed to load the dataframe."},
            status_code=400,
        )

    # Extract Schema, Data Dictionary, and Summary (summary unused here)
    schema, data_dictionary, _summary, error_response = build_context(df)
    if error_response is not None:
        return error_response
    # If not confirm, just return the count of the query results
    if not confirm:
        # Generate Pandas Query
        pandas_query = generate_pandas_query(question, schema, data_dictionary)

        if not pandas_query:
            logger.error("Failed to generate a valid pandas query.")
            return JSONResponse(
                content={"error": "Failed to generate a valid pandas query."},
                status_code=400,
            )

        pandas_query = strip_code_fences(pandas_query)
        if not is_code_safe(pandas_query):
            logger.error(f"Generated code failed safety check: {pandas_query}")
            return JSONResponse(
                content={"error": "Generated query failed a safety check."},
                status_code=400,
            )

        # Execute Query
        _vars = {"df": df, 'query_result': None, 'pd': pd}
        try:
            exec(pandas_query, _vars)
            query_result = _vars.get('query_result', None)
            if query_result is None:
                raise ValueError("The generated query did not assign a value to 'query_result'.")

            # Determine the count
            if isinstance(query_result, (pd.DataFrame, list, dict, set, tuple)):
                count = len(query_result)
            else:
                count = 1  # For scalar results
            logger.info(f"Number of query results for visualization: {count}")

        except Exception as e:
            logger.error(f"Failed to execute query: {e}")
            return JSONResponse(
                content={"error": f"Failed to execute query: {e}"},
                status_code=400,
            )

        return {"count": count}
    else:
        # If confirm=True, generate the final Plotly visualization
        plotly_code = generate_plotly_code(question, schema)

        if not plotly_code:
            logger.error("Failed to generate Plotly code.")
            return JSONResponse(
                content={"error": "Failed to generate Plotly code."},
                status_code=400,
            )

        plotly_json = get_plotly_json(plotly_code, df)

        if not plotly_json:
            logger.error("Failed to generate Plotly JSON.")
            return JSONResponse(
                content={"error": "Failed to generate Plotly JSON."},
                status_code=400,
            )

        logger.info("Plotly JSON generated successfully.")
        return JSONResponse(content={"plotly_json": plotly_json})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
