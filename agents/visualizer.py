# agents/visualizer.py

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import os
import plotly.io as pio
import plotly.graph_objects as go
import plotly.express as px  # Import Plotly Express
import logging
from rich.console import Console
import ast
import pandas as pd

from utils.code_safety import strip_code_fences, is_code_safe

console = Console()
load_dotenv()

# Initialize the logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Initialize the OpenAI LLM with LangChain
llm = ChatOpenAI(temperature=0, model_name="gpt-4o")

def generate_plotly_code(question, schema):
    logger.info("Generating Plotly code.")
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "human",
                """
                You are a data visualization expert. Based on the following schema and question, generate Plotly code to visualize the data appropriately.
                Provide only the Python code that creates a Plotly figure named 'fig'. Do not include any explanations or comments.
                Do not include code to read the dataframe; assume the dataframe is provided as 'df'.
                Ensure that all arguments to Plotly functions come from the same DataFrame to avoid length mismatches.
                Do not include any commands that display or show the figure, such as `fig.show()`.
                You may use Plotly Express (available as px) or Plotly Graph Objects (available as go).
                DO NOT include any import statements (e.g., do not write "import plotly.express as px"). 
                Do not use triple backticks.
                Do not use  ```python```, just use plain text.

                Schema:
                {schema}

                Plotly Code:
                """,
            ),
            ("human", "{question}"),
        ]
    )

    chain = prompt | llm
    _input = {"schema": schema, "question": question}

    try:
        response = chain.invoke(_input)
    except Exception as e:
        logger.error(f"LLM call failed while generating Plotly code: {e}")
        return None

    logger.debug(f"LLM response: {response.content}")

    # Extract the code (assuming the response contains only the code)
    code = response.content.strip()
    console.log(f"Generated code: {code}")

    plotly_code = code
    logger.info(f"Generated Plotly code: {plotly_code}")
    return plotly_code


def validate_plotly_code(plotly_code, df):
    """
    Validates that the generated Plotly code creates a 'fig' object and that
    the 'x', 'y', and 'text' arguments (if any) have consistent lengths.
    """
    try:
        tree = ast.parse(plotly_code)
        plot_call = None
        plot_type = None

        # Find any function call of the form px.<something>(...)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == 'px':
                    plot_call = node
                    plot_type = node.func.attr  # e.g., 'bar', 'box', etc.
                    break

        if not plot_call:
            raise ValueError("No px.<plot_type> call found in the generated code.")

        args = {}
        for keyword in plot_call.keywords:
            args[keyword.arg] = keyword.value

        # Ensure 'x' and 'y' are present
        if 'x' not in args or 'y' not in args:
            raise ValueError("'x' and 'y' arguments are required in the Plotly express call.")

        # Extract column names from 'x' and 'y'
        def extract_column(arg_node):
            if isinstance(arg_node, ast.Str):
                return arg_node.s
            elif isinstance(arg_node, ast.Constant) and isinstance(arg_node.value, str):
                return arg_node.value
            else:
                raise ValueError("Unsupported argument type for 'x' or 'y'.")

        x_col = extract_column(args['x'])
        y_col = extract_column(args['y'])

        # Check if columns exist in DataFrame
        if x_col not in df.columns or y_col not in df.columns:
            raise ValueError(f"Columns '{x_col}' and/or '{y_col}' not found in dataframe.")

        # Check lengths
        x_length = len(df[x_col])
        y_length = len(df[y_col])

        if 'text' in args:
            text_col = extract_column(args['text'])
            if text_col not in df.columns:
                raise ValueError(f"Text column '{text_col}' not found in dataframe.")
            text_length = len(df[text_col])
            if text_length != x_length or text_length != y_length:
                raise ValueError("Length mismatch between 'x', 'y', and 'text' arguments.")

        return True

    except Exception as e:
        logger.error(f"Validation error: {e}")
        return False


def get_plotly_json(plotly_code, df):
    logger.info("Generating Plotly JSON.")
    # Prepare a namespace for exec
    namespace = {
        'df': df,
        'go': go,
        'pio': pio,
        'pd': pd,
        'px': px  # Include Plotly Express in the namespace
    }
    try:
        plotly_code = strip_code_fences(plotly_code)
        if not is_code_safe(plotly_code):
            raise ValueError("Generated Plotly code failed a safety check.")

        exec(plotly_code, namespace)
        fig = namespace.get('fig', None)
        if fig is None:
            raise ValueError("Plotly code did not create a figure named 'fig'.")

        # Convert figure to JSON
        fig_json = fig.to_json()
        logger.info("Plotly JSON generated successfully.")
        return fig_json
    except Exception as e:
        logger.error(f"Error generating Plotly JSON: {e}")
        return None
