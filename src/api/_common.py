from typing import Any

from fastapi import HTTPException


def ok(data: Any) -> dict:
    return {"ok": True, "data": data, "error": None}


def api_error(code: str, message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )
