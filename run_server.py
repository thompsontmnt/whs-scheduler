"""Launcher for the scheduler web app.

Explicitly seeds sys.path so the preview tool's subprocess can find
installed packages regardless of its working directory or environment.
"""
import sys
import os

# Ensure user and system site-packages are on the path
_PATHS = [
    "/Users/mikethompson/Library/Python/3.9/lib/python/site-packages",
    "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/site-packages",
]
for p in _PATHS:
    if p not in sys.path:
        sys.path.insert(0, p)

# Ensure the project root is on the path
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "scheduler.app:app",
        host="0.0.0.0",
        port=8000,
        loop="asyncio",
        http="h11",
    )
