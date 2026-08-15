from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

_MUTATING = frozenset({"POST", "PATCH", "PUT", "DELETE"})
_SKIP_PATHS = frozenset({"/api/v1/healthz", "/api/v1/readyz"})


def _csrf_rejected() -> JSONResponse:
    return JSONResponse(
        status_code=403,
        media_type="application/problem+json",
        content={
            "type": "https://nexus.crm/problems/csrf_rejected",
            "title": "Solicitud rechazada",
            "status": 403,
            "detail": "Encabezado X-Nexus-Client inválido.",
            "code": "csrf_rejected",
        },
    )


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path.rstrip("/") or "/"
        if request.method in _MUTATING and path not in _SKIP_PATHS:
            if request.headers.get("X-Nexus-Client") != "web":
                return _csrf_rejected()
        return await call_next(request)
