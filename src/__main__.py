import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8001, reload=False)
