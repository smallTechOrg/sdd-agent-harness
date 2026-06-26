import sys
from pathlib import Path

# `python -m src` puts the repo root on sys.path[0], not `src/`. The app modules
# (`api`, `db`, ...) are imported as bare top-level names throughout the codebase
# (matching the test config's `pythonpath=["src"]`). Ensure the directory that
# contains them — this file's parent, i.e. `src/` — is importable before launch.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn

from api import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=False)
