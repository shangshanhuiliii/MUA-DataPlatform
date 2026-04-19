from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi.responses import JSONResponse


class AppError(Exception):
    """Structured application error with stable business code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.headers = headers or {}
        self.extra = extra or {}

    def payload(self) -> Dict[str, Any]:
        payload = {"code": self.code, "detail": self.detail}
        payload.update(self.extra)
        return payload

    def to_response(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code,
            content=self.payload(),
            headers=self.headers,
        )


def app_error(
    status_code: int,
    code: str,
    detail: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    **extra: Any,
) -> AppError:
    return AppError(
        status_code=status_code,
        code=code,
        detail=detail,
        headers=headers,
        extra=extra or None,
    )
