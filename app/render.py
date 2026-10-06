from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from app.config import get_settings
from app.flash import clear_flash, read_flash

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
settings = get_settings()

# Branding (app_name / app_short_name) can be overridden at runtime from
# Administration > System Settings. Cached in-process and invalidated
# explicitly on save, rather than hitting the DB on every single page render.
_branding_cache: dict | None = None


def invalidate_branding_cache() -> None:
    global _branding_cache
    _branding_cache = None


def _effective_settings():
    global _branding_cache
    if _branding_cache is None:
        from app.database import SessionLocal
        from app.services.settings_service import get_setting_str

        db = SessionLocal()
        try:
            _branding_cache = {
                "app_name": get_setting_str(db, "app_name", settings.app_name),
                "app_short_name": get_setting_str(db, "app_short_name", settings.app_short_name),
            }
        finally:
            db.close()
    if _branding_cache["app_name"] == settings.app_name and _branding_cache["app_short_name"] == settings.app_short_name:
        return settings
    return settings.model_copy(update=_branding_cache)


def _make_qs(request: Request):
    def qs(**overrides) -> str:
        params = dict(request.query_params)
        for k, v in overrides.items():
            params[k] = str(v)
        return "&".join(f"{k}={v}" for k, v in params.items())

    return qs


def render(request: Request, name: str, context: dict | None = None, status_code: int = 200) -> Response:
    context = dict(context or {})
    context.setdefault("request", request)
    context.setdefault("settings", _effective_settings())
    context.setdefault("user", getattr(request.state, "user", None))
    context.setdefault("flash_messages", read_flash(request))
    context.setdefault("qs", _make_qs(request))
    response = templates.TemplateResponse(request, name, context, status_code=status_code)
    clear_flash(request, response)
    return response
