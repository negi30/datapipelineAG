# agents/query_generator.py

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import os
import logging
from rich.console import Console

console = Console()
load_dotenv()

# Initialize the logger
logger = logging.getLogger(__name__)

# Initialize the OpenAI LLM with LangChain
llm = ChatOpenAI(temperature=0, model_name="gpt-4o")

def generate_pandas_query(question, schema, data_dictionary):
    logger.info("Generating pandas query.")

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "human",
                """
                You are a data analyst. Based on the following schema, data dictionary and question, generate an efficient pandas query.
                Return only the pandas query code without any explanations. You should return the code not human-like text.
                The code should not have any comments.
                You should not put any code in triple backticks.
                Do not use  ```python```, just use plain text.
                The query result should be store in a variable named 'query_result'
                If user asked about the whole dataset without any sepecific query, you just return query_result=df.head()
                If user asked for help in a decision, generate a good pandas query based on schema to help him. 
                Note that, when you want generate a query like df["columnX"] == "value", you should note the "value" be in provided unique values of columnX.
                When users question is about a specific district, your query should be filtered on that district.
                When users question is about a specific product, your query should be filtered on that product conisdering provided unique values.

                For example: 
                    query_result = df[["column1", "column2"]]

                Schema:
                {schema}

                Data Dictionary:
                {data_dictionary}

                Pandas Query:
                """,
            ),
            ("human", "{question}"),
        ]
    )
    chain = prompt | llm 
    _input = {"schema": schema, "question": question, "data_dictionary": data_dictionary}

    try:
        response = chain.invoke(_input)
    except Exception as e:
        logger.error(f"LLM call failed while generating pandas query: {e}")
        return None

    # Extract the query code from the response
    code = response.content.strip()
    console.log(f"Generated code: {code}")

    # Sanitize and validate the code if necessary
    # if 'query' in code:
    #     try:
    #         exec_globals = {}
    #         exec(code, {}, exec_globals)
    #         pandas_query = exec_globals.get("query", "")
    #     except Exception as e:
    #         logger.error(f"Error executing generated code: {e}")
    #         pandas_query = ""
    # else:
    #     pandas_query = code  # Assuming the code itself is the query string

    pandas_query = code
    logger.info(f"Generated pandas query: {pandas_query}")
    return pandas_query
