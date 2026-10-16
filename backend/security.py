"""Same-origin browser access and bearer authentication for native clients."""
import asyncio
import hmac
import ipaddress
from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

MAX_BODY = 256 * 1024
COOKIE = "evo16_session"


def valid_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_private or ip in ipaddress.ip_network("100.64.0.0/10")
    except ValueError:
        return False


class AccessControl(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not valid_host(request.url.hostname or ""):
            return JSONResponse({"detail": "Host no permitido"}, 400)
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.url.netloc}"
        if origin and origin != expected:
            return JSONResponse({"detail": "Origen no permitido"}, 403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Solicitud entre sitios no permitida"}, 403)
        # Count actual bytes too: Content-Length may be absent (chunked) or dishonest.
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            body = bytearray()
            try:
                async with asyncio.timeout(5):
                    async for chunk in request.stream():
                        body.extend(chunk)
                        if len(body) > MAX_BODY:
                            return JSONResponse({"detail": "Solicitud demasiado grande"}, 413)
            except TimeoutError:
                return JSONResponse({"detail": "Tiempo de recepción agotado"}, 408)
            request._body = bytes(body)
        if request.url.path.startswith("/api/"):
            token = request.app.state.token
            supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
            bearer = bool(supplied) and hmac.compare_digest(supplied, token)
            cookie = request.cookies.get(COOKIE, "")
            session = bool(cookie) and hmac.compare_digest(cookie, token)
            if session and request.method not in {"GET", "HEAD"} and origin != expected:
                session = False
            if not (bearer or session):
                return JSONResponse({"detail": "Autenticación requerida"}, 401,
                                    headers={"WWW-Authenticate": "Bearer"})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response
