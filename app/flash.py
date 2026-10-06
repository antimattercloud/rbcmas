import json
import urllib.parse

from fastapi import Request, Response

FLASH_COOKIE = "rbcmas_flash"


def set_flash(response: Response, category: str, message: str) -> None:
    payload = urllib.parse.quote(json.dumps([[category, message]]))
    response.set_cookie(FLASH_COOKIE, payload, max_age=15, httponly=True, samesite="lax")


def read_flash(request: Request) -> list[tuple[str, str]]:
    raw = request.cookies.get(FLASH_COOKIE)
    if not raw:
        return []
    try:
        data = json.loads(urllib.parse.unquote(raw))
        return [(c, m) for c, m in data]
    except (ValueError, TypeError):
        return []


def clear_flash(request: Request, response: Response) -> None:
    if request.cookies.get(FLASH_COOKIE):
        response.delete_cookie(FLASH_COOKIE)
