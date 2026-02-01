#!/usr/bin/env python3
"""Launch Mac Disk Declutter."""

import webbrowser
import threading
from backend.app import app

URL = "http://127.0.0.1:5192"

def open_browser():
    webbrowser.open(URL)

if __name__ == "__main__":
    threading.Timer(1.5, open_browser).start()
    print(f"Starting Mac Disk Declutter at {URL}")
    app.run(host="127.0.0.1", port=5192, debug=False)
