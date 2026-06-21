import uvicorn

from .config import get_settings

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run("src.server:app", host="0.0.0.0", port=s.port, reload=False)
