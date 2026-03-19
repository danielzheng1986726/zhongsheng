"""Second Me OAuth2 routes — login, callback, logout, me."""

import os
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import URLSafeTimedSerializer

from services import secondme, database

router = APIRouter(prefix="/api/auth", tags=["auth"])

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    import secrets
    SECRET_KEY = secrets.token_hex(32)
    import logging
    logging.getLogger("auth").warning("SECRET_KEY not set — generated random key (sessions won't survive restart)")
COOKIE_NAME = "zs_session"
MAX_AGE = 7 * 24 * 3600  # 7 days

_signer = URLSafeTimedSerializer(SECRET_KEY)

SECONDME_CLIENT_ID = os.getenv("SECONDME_CLIENT_ID", "1709f9d0-7c9f-4d6e-b45e-fa7386ed0772")
OAUTH_BASE = "https://go.second.me/oauth/"


def _base_url(request: Request) -> str:
    base = os.getenv("BASE_URL", "")
    # Ignore platform-injected internal hostnames (e.g. koyeb.app)
    if base and ".koyeb.app" not in base:
        return base.rstrip("/")
    return "https://zhongsheng.ai-builders.space"


def _set_session(response: Response, data: dict):
    token = _signer.dumps(data)
    response.set_cookie(
        COOKIE_NAME, token, max_age=MAX_AGE,
        httponly=True, samesite="lax", secure=True,
    )


def _get_session(request: Request) -> dict | None:
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    try:
        return _signer.loads(cookie, max_age=MAX_AGE)
    except Exception:
        return None


@router.get("/login")
async def login(request: Request):
    """Redirect to Second Me OAuth authorization page."""
    redirect_uri = f"{_base_url(request)}/api/auth/callback"
    params = urlencode({
        "client_id": SECONDME_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "user_info,chat,act,memory",
    })
    return RedirectResponse(f"{OAUTH_BASE}?{params}")


@router.get("/callback")
async def callback(request: Request, code: str = ""):
    """Handle OAuth callback — exchange code for tokens, set session cookie."""
    if not code:
        return RedirectResponse("/?error=no_code")

    redirect_uri = f"{_base_url(request)}/api/auth/callback"
    try:
        token_data = await secondme.exchange_code(code, redirect_uri)
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token", "")

        user_info = await secondme.get_user_info(access_token)

        user_name = user_info.get("name", "用户")
        user_avatar = user_info.get("avatar", "")

        session = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_name": user_name,
            "user_avatar": user_avatar,
        }

        # Persist user tokens to DB for background agent comments
        if database.is_enabled():
            database.upsert_user(user_name, user_avatar, access_token, refresh_token)
            database.sync()

        # Close popup and notify parent page
        html = """<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
        <p>登录成功，正在返回…</p>
        <script>
        if (window.opener) {
            try { window.opener._onLoginSuccess(); } catch(e) {}
            window.close();
        } else {
            window.location.href = '/';
        }
        </script></body></html>"""
        response = HTMLResponse(html)
        _set_session(response, session)
        return response
    except Exception as e:
        import logging
        logging.getLogger("auth").exception("OAuth callback failed")
        from urllib.parse import quote
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
        <p>登录失败：{quote(str(e))}</p>
        <script>setTimeout(function(){{ window.close(); }}, 3000);</script>
        </body></html>"""
        return HTMLResponse(html, status_code=400)


@router.get("/logout")
async def logout():
    """Clear session cookie and redirect home."""
    response = RedirectResponse("/")
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/me")
async def me(request: Request):
    """Return current user info or logged-out status."""
    session = _get_session(request)
    if not session:
        return {"logged_in": False}
    return {
        "logged_in": True,
        "name": session.get("user_name", ""),
        "avatar": session.get("user_avatar", ""),
    }
