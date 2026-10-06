from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.database import SessionLocal
from app.render import render
from app.security import SESSION_COOKIE_NAME, NotAuthenticated, PermissionDenied, read_session_token

settings = get_settings()
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title=settings.app_name, docs_url="/api/docs" if settings.debug else None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class CurrentUserMiddleware(BaseHTTPMiddleware):
    """Attaches request.state.user so templates can render nav/branding
    without every single route re-deriving the logged-in user."""

    async def dispatch(self, request: Request, call_next):
        request.state.user = None
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if token:
            user_id = read_session_token(token)
            if user_id:
                db = SessionLocal()
                try:
                    from app.models.user import User

                    user = db.get(User, user_id)
                    if user and user.is_active:
                        request.state.user = user
                finally:
                    db.close()
        return await call_next(request)


app.add_middleware(CurrentUserMiddleware)

from app.routers import (  # noqa: E402
    admin,
    analytics,
    audit,
    auth,
    chemicals,
    containers,
    data_io,
    dashboard,
    laboratories,
    locations,
    procurement,
    reports,
    search,
    transfers,
    usage,
    verification,
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(chemicals.router)
app.include_router(containers.router)
app.include_router(laboratories.router)
app.include_router(locations.router)
app.include_router(usage.router)
app.include_router(transfers.router)
app.include_router(verification.router)
app.include_router(procurement.router)
app.include_router(analytics.router)
app.include_router(reports.router)
app.include_router(audit.router)
app.include_router(data_io.router)
app.include_router(search.router)
app.include_router(admin.router)


async def handle_not_authenticated(request: Request, exc: NotAuthenticated):
    return RedirectResponse("/login", status_code=302)


async def handle_permission_denied(request: Request, exc: PermissionDenied):
    return render(request, "errors/403.html", {"nav_active": ""}, status_code=403)


async def friendly_http_exception(request: Request, exc):
    if exc.status_code == 404:
        return render(request, "errors/404.html", {"nav_active": ""}, status_code=404)
    if exc.status_code in (401, 403):
        # Defensive fallback in case a plain HTTPException(401/403) is ever raised
        # directly instead of the NotAuthenticated/PermissionDenied exceptions above.
        return RedirectResponse("/login", status_code=302) if exc.status_code == 401 else render(
            request, "errors/403.html", {"nav_active": ""}, status_code=403
        )
    return render(request, "errors/500.html", {"nav_active": "", "detail": getattr(exc, "detail", "")}, status_code=exc.status_code)


app.add_exception_handler(NotAuthenticated, handle_not_authenticated)
app.add_exception_handler(PermissionDenied, handle_permission_denied)
app.add_exception_handler(HTTPException, friendly_http_exception)
app.add_exception_handler(StarletteHTTPException, friendly_http_exception)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_short_name}
