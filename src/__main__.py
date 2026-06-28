import os
import sys

import uvicorn

if __name__ == "__main__":
    # When launched as ``python -m src`` from the repo root, ``src/`` is NOT on
    # sys.path, so the bare import ``api:app`` (used everywhere via the
    # pyproject ``pythonpath=["src"]`` pytest setting) is unresolvable. Put the
    # directory containing this file (``src/``) at the front of sys.path so
    # uvicorn's string import target ``api:app`` resolves identically to tests.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    uvicorn.run("api:app", host="0.0.0.0", port=8001, reload=False)
