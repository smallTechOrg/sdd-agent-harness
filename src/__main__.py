"""Entry point: ``uv run python -m src`` starts the single-origin server on :8001.

``src/`` is the package root and bare imports (``from api import app``) resolve
against it. ``python -m src`` puts the repo root (the parent of ``src/``) on
``sys.path`` but NOT ``src/`` itself, so ``import api`` would fail. Insert this
file's own directory (``src/``) onto the path so the uvicorn import string
``api:app`` resolves the same way the tests' ``pythonpath = ["src"]`` does.
"""
import os
import sys

import uvicorn

# Ensure src/ (this file's directory) is importable so "api:app" resolves.
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8001"))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False)
