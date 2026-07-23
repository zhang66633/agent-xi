"""简单密码门 — 保护 Web UI 不被陌生人白嫖 token。

流程：无 cookie → 跳转 /login → 输密码 → 设 cookie → 正常使用。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from fastapi import Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

# 用于签名 cookie 的密钥（每次启动随机，重启后需重新登录）
_SECRET = secrets.token_hex(32)

COOKIE_NAME = "xi_session"

# 不需要鉴权的路径
_PUBLIC_PATHS = {"/login", "/api/health"}


def _get_password() -> str:
    """延迟读取密码（确保 load_dotenv 已执行）。"""
    return os.environ.get("XI_ACCESS_PASSWORD", "")


def _make_token(password: str) -> str:
    """用 HMAC 签名密码，生成 cookie 值。"""
    return hmac.new(
        _SECRET.encode(), password.encode(), hashlib.sha256
    ).hexdigest()


def _verify_token(token: str) -> bool:
    """校验 cookie 值是否合法。"""
    pwd = _get_password()
    if not pwd:
        return True  # 未设密码 → 不鉴权
    expected = _make_token(pwd)
    return hmac.compare_digest(token, expected)


LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Xi - Login</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: #1a1a2e; font-family: monospace;
  }
  .box {
    background: #16213e; border: 2px solid #0f3460; padding: 2rem;
    width: 320px; text-align: center;
  }
  h1 { color: #e94560; font-size: 1.5rem; margin-bottom: 0.5rem; }
  p { color: #a0a0b0; font-size: 0.85rem; margin-bottom: 1.5rem; }
  input {
    width: 100%; padding: 0.6rem; margin-bottom: 1rem;
    background: #0f3460; border: 1px solid #533483; color: #eee;
    font-family: monospace; font-size: 1rem; outline: none;
  }
  input:focus { border-color: #e94560; }
  button {
    width: 100%; padding: 0.6rem; background: #e94560; color: #fff;
    border: none; font-family: monospace; font-size: 1rem; cursor: pointer;
  }
  button:hover { background: #c73e54; }
  .err { color: #e94560; font-size: 0.8rem; margin-top: 0.5rem; display: none; }
</style>
</head>
<body>
<div class="box">
  <h1>Agent Xi</h1>
  <p>输入访问密码</p>
  <form method="post" action="/login">
    <input type="password" name="password" placeholder="password" autofocus>
    <button type="submit">Enter</button>
  </form>
  <div class="err" id="err">密码错误</div>
</div>
<script>
  if (location.search.includes('error')) document.getElementById('err').style.display = 'block';
</script>
</body>
</html>"""


class AuthMiddleware(BaseHTTPMiddleware):
    """密码门中间件。未设 XI_ACCESS_PASSWORD 时完全透明。"""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # 未设密码 → 不鉴权
        password = _get_password()
        if not password:
            return await call_next(request)

        path = request.url.path

        # 公开路径放行
        if path in _PUBLIC_PATHS:
            return await call_next(request)

        # 登录页 GET
        if path == "/login" and request.method == "GET":
            return HTMLResponse(LOGIN_HTML)

        # 登录 POST
        if path == "/login" and request.method == "POST":
            form = await request.form()
            pwd = form.get("password", "")
            if pwd == password:
                resp = RedirectResponse("/", status_code=302)
                resp.set_cookie(
                    COOKIE_NAME,
                    _make_token(pwd),
                    httponly=True,
                    max_age=86400 * 30,  # 30 天
                    samesite="lax",
                )
                return resp
            return RedirectResponse("/login?error=1", status_code=302)

        # 普通请求：检查 cookie
        token = request.cookies.get(COOKIE_NAME, "")
        if not _verify_token(token):
            return RedirectResponse("/login", status_code=302)

        return await call_next(request)
