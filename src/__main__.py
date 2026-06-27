import os
import sys
from pathlib import Path

import uvicorn

# `python -m src` runs with the repo root on sys.path, but the application
# modules (api, db, graph, ...) are top-level packages *inside* src/. Add this
# directory to sys.path so uvicorn's string import "api:app" resolves.
_SRC_DIR = str(Path(__file__).resolve().parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8001")),
        reload=False,
    )
