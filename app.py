#!/usr/bin/env python3
"""
Local launcher for the DataChat AI Agent application.
Runs Uvicorn on port 8000 and opens the browser.
"""

import sys
import os
import webbrowser
import threading
import time

try:
    import uvicorn
except ImportError:
    print("Error: Uvicorn is not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

def open_browser(port):
    time.sleep(1.2)
    url = f"http://localhost:{port}"
    print(f"\n🚀 Opening web interface at {url} ...\n")
    webbrowser.open(url)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")

    print("=" * 65)
    print("  📊 DataChat AI Agent - 10MB Dataset Analytics & Runner")
    print("=" * 65)
    print(f"  Server URL: http://{host}:{port}")
    print(f"  API Docs:   http://{host}:{port}/docs")
    print(f"  Dataset:    sample_retail_data.csv (or upload custom up to 10MB)")
    print("=" * 65)

    threading.Thread(target=open_browser, args=(port,), daemon=True).start()

    uvicorn.run("api.index:app", host=host, port=port, reload=True)
