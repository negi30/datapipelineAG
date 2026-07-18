#!/bin/bash

# Start FastAPI in the background
echo "Starting FastAPI..."
python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload &
FASTAPI_PID=$!
echo "FastAPI started with PID $FASTAPI_PID"

# Start Streamlit in the background
echo "Starting Streamlit..."
python3 -m streamlit run streamlit_app.py &
STREAMLIT_PID=$!
echo "Streamlit started with PID $STREAMLIT_PID"

# Function to terminate both services
terminate_services() {
    echo "Terminating FastAPI and Streamlit..."
    kill $FASTAPI_PID
    kill $STREAMLIT_PID
    exit 0
}

# Trap SIGINT (Ctrl+C) and terminate services
trap terminate_services SIGINT

# Wait for both services to finish
wait $FASTAPI_PID
wait $STREAMLIT_PID
