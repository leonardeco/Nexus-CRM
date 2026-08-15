from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status: int, code: str, title: str, detail: str) -> None:
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail


def _problem(status: int, code: str, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": f"https://nexus.crm/problems/{code}",
            "title": title,
            "status": status,
            "detail": detail,
            "code": code,
        },
    )


def register_errors(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_req: Request, exc: AppError) -> JSONResponse:
        return _problem(exc.status, exc.code, exc.title, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(
        _req: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return _problem(
            422,
            "validation_error",
            "Datos inválidos",
            "Revisa los campos enviados.",
        )
