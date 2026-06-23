import sys
from pathlib import Path

# Ensure top-level package imports (api, graph, config, ...) resolve when launched
# via `python -m src` (which puts the repo root, not src/, on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn
from api import app  # now resolvable

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=False)
