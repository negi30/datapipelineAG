# run_all.py

import subprocess
import sys
import os
import argparse
import signal
import threading

def run_fastapi():
    """
    Starts the FastAPI server using uvicorn as a module.
    """
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

def run_streamlit():
    """
    Starts the Streamlit app.
    Assumes that 'streamlit_app.py' is the Streamlit application file.

    Invoked as `python -m streamlit` rather than the bare `streamlit`
    command: on Windows the Scripts/ folder that holds streamlit.exe
    isn't always on PATH even when streamlit is installed correctly,
    which raises FileNotFoundError ([WinError 2]) from subprocess.Popen.
    Using sys.executable guarantees we call the interpreter (and its
    installed packages) that's actually running this script.
    """
    return subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "streamlit_app.py", "--server.maxUploadSize", "300"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

def stream_output(process, name):
    """
    Reads the output from a subprocess and prints it with a prefix.
    """
    for line in iter(process.stdout.readline, ''):
        print(f"[{name}]: {line}", end='')

def stream_error(process, name):
    """
    Reads the error output from a subprocess and prints it with a prefix.
    """
    for line in iter(process.stderr.readline, ''):
        print(f"[{name}]: {line}", end='')

def main():
    parser = argparse.ArgumentParser(description="Run FastAPI and Streamlit")
    parser.add_argument('--backend', action='store_true', help='Run FastAPI backend only')
    parser.add_argument('--frontend', action='store_true', help='Run Streamlit frontend only')
    parser.add_argument('--all', action='store_true', help='Run both FastAPI and Streamlit')

    args = parser.parse_args()

    processes = []

    if args.all or (not args.backend and not args.frontend):
        # Default action: run both if no specific option is provided
        print("Starting FastAPI and Streamlit...")
        fastapi_process = run_fastapi()
        streamlit_process = run_streamlit()
        processes.extend([fastapi_process, streamlit_process])

        # Start threads to stream output
        threading.Thread(target=stream_output, args=(fastapi_process, "FastAPI"), daemon=True).start()
        threading.Thread(target=stream_error, args=(fastapi_process, "FastAPI"), daemon=True).start()
        threading.Thread(target=stream_output, args=(streamlit_process, "Streamlit"), daemon=True).start()
        threading.Thread(target=stream_error, args=(streamlit_process, "Streamlit"), daemon=True).start()
    else:
        if args.backend:
            print("Starting FastAPI...")
            fastapi_process = run_fastapi()
            processes.append(fastapi_process)
            threading.Thread(target=stream_output, args=(fastapi_process, "FastAPI"), daemon=True).start()
            threading.Thread(target=stream_error, args=(fastapi_process, "FastAPI"), daemon=True).start()
        if args.frontend:
            print("Starting Streamlit...")
            streamlit_process = run_streamlit()
            processes.append(streamlit_process)
            threading.Thread(target=stream_output, args=(streamlit_process, "Streamlit"), daemon=True).start()
            threading.Thread(target=stream_error, args=(streamlit_process, "Streamlit"), daemon=True).start()

    def shutdown(signum, frame):
        """
        Handles shutdown signals to terminate subprocesses gracefully.
        """
        print("\nShutting down...")
        for proc in processes:
            proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=5)
                print(f"Terminated {proc.args[0]}")
            except subprocess.TimeoutExpired:
                proc.kill()
                print(f"Killed {proc.args[0]}")
        sys.exit(0)

    # Register the shutdown function for SIGINT and SIGTERM
    # signal.signal(signal.SIGINT, shutdown)
    # signal.signal(signal.SIGTERM, shutdown)

    # Wait for all processes to complete
    try:
        for proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        shutdown(None, None)

if __name__ == "__main__":
    main()
