import os
import sys
from pathlib import Path

# Ensure src/ is on sys.path so sub-packages (api, graph, db, etc.) are importable
_src = Path(__file__).parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import uvicorn
from observability.events import configure_logging
from config.settings import get_settings

if __name__ == "__main__":
    s = get_settings()
    configure_logging(s.log_level)
    # Render (and most PaaS) inject the port to bind via $PORT; fall back to 8001 locally.
    port = int(os.environ.get("PORT", "8001"))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False)
