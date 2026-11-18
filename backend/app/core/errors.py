"""Format d'erreur unique de l'API : {"detail": "...", "code": "..."} (docs/architecture.md, règle 3)."""
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

DEFAULT_CODES = {
    400: "BAD_REQUEST",
    401: "NOT_AUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


class ApiError(HTTPException):
    """HTTPException avec un code machine stable, documenté dans docs/api.md."""

    def __init__(self, status_code: int, detail: str, code: str | None = None, headers: dict | None = None):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code or DEFAULT_CODES.get(status_code, "ERROR")


async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = getattr(exc, "code", None) or DEFAULT_CODES.get(exc.status_code, "ERROR")
    return JSONResponse(
        {"detail": exc.detail, "code": code}, status_code=exc.status_code, headers=getattr(exc, "headers", None)
    )


async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {"field": ".".join(str(part) for part in err.get("loc", ())), "message": err.get("msg", "")}
        for err in exc.errors()
    ]
    return JSONResponse(
        {"detail": "Données invalides", "code": "VALIDATION_ERROR", "errors": errors}, status_code=422
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
