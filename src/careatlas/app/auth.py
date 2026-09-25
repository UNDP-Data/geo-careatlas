"""Session checks against oauth2-proxy.

oauth2-proxy owns the GitHub login flow and the session cookie. The app forwards
the browser's cookie to the proxy's ``/auth`` endpoint, which answers 202 with
``X-Auth-Request-*`` headers for a valid session and 401 otherwise.
"""

import logging
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from starlette.requests import HTTPConnection

from careatlas.app.config import settings

logger = logging.getLogger(__name__)

_client = httpx.AsyncClient(timeout=3.0)

# oauth2-proxy's default cookie name; large sessions are split into _oauth2_proxy_0, _1, ...
SESSION_COOKIE_PREFIX = "_oauth2_proxy"
# Pages such as the notebook editor load hundreds of assets, each checked
# separately. Caching a confirmed session briefly avoids one oauth2-proxy call
# per asset; revoked access takes effect within this many seconds.
CACHE_SECONDS = 30
CACHE_LIMIT = 1000
_cache: dict[str, tuple[float, "User"]] = {}


@dataclass(frozen=True)
class User:
    username: str
    email: str
    groups: tuple[str, ...] = ()

    @property
    def display_name(self) -> str:
        return self.username or self.email


async def get_user(request: HTTPConnection) -> User | None:
    """Return the signed-in user, or None for anonymous visitors."""
    cookie = session_cookie(request.headers.get("cookie", ""))
    if not settings.auth_enabled or not cookie:
        return None

    cached = _cache.get(cookie)
    if cached and cached[0] > time.monotonic():
        return cached[1]

    try:
        response = await _client.get(f"{settings.auth_internal_url}/auth", headers={"Cookie": cookie})
    except httpx.HTTPError as exc:
        logger.warning("oauth2-proxy unreachable at %s: %s", settings.auth_internal_url, exc)
        return None

    if response.status_code not in (200, 202):
        return None

    headers = response.headers
    groups = tuple(g.strip() for g in headers.get("x-auth-request-groups", "").split(",") if g.strip())
    user = User(
        username=headers.get("x-auth-request-user", ""),
        email=headers.get("x-auth-request-email", ""),
        groups=groups,
    )
    if len(_cache) >= CACHE_LIMIT:
        now = time.monotonic()
        for key in [k for k, (expires, _) in _cache.items() if expires <= now] or list(_cache)[: CACHE_LIMIT // 2]:
            _cache.pop(key, None)
    _cache[cookie] = (time.monotonic() + CACHE_SECONDS, user)
    return user


def session_cookie(header: str) -> str:
    """The oauth2-proxy session cookies from a Cookie header, as a Cookie header value."""
    pairs = []
    for part in header.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name.startswith(SESSION_COOKIE_PREFIX):
            pairs.append(f"{name}={value}")
    return "; ".join(sorted(pairs))


def page_url(request: HTTPConnection) -> str:
    """Absolute URL of the current page as the browser sees it."""
    path = request.url.path
    if request.url.query:
        path += f"?{request.url.query}"
    if settings.public_url:
        return settings.public_url + path
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    return f"{scheme}://{host}{path}"


def sign_in_url(request: HTTPConnection) -> str:
    return f"{settings.auth_public_url}/start?{urlencode({'rd': page_url(request)})}"


def sign_out_url(request: HTTPConnection) -> str:
    return f"{settings.auth_public_url}/sign_out?{urlencode({'rd': page_url(request)})}"


async def close() -> None:
    await _client.aclose()
