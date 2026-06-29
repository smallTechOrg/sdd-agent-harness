import os
import sys

import uvicorn

# Ensure the package root (this directory, `src/`) is importable so uvicorn can
# resolve the bare `api:app` import string regardless of how the process is
# launched (`uv run python -m src`). pyproject's `pythonpath` only applies under
# pytest, not the run path.
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8001, reload=False)
