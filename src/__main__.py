import sys
from pathlib import Path

# Ensure src/ is on sys.path so data_analysis package is importable
# when run via `uv run python -m src`
_src_dir = str(Path(__file__).parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import uvicorn

if __name__ == "__main__":
    uvicorn.run("data_analysis.api:app", host="0.0.0.0", port=8001, reload=False)
