"""Session checks against oauth2-proxy.

oauth2-proxy owns the GitHub login flow and the session cookie. The app forwards
the browser's cookie to the proxy's ``/auth`` endpoint, which answers 202 with
``X-Auth-Request-*`` headers for a valid session and 401 otherwise.
"""

import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from starlette.requests import HTTPConnection

from careatlas.app.config import settings

logger = logging.getLogger(__name__)

_client = httpx.AsyncClient(timeout=3.0)


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
    cookie = request.headers.get("cookie")
    if not settings.auth_enabled or not cookie:
        return None

    try:
        response = await _client.get(f"{settings.auth_internal_url}/auth", headers={"Cookie": cookie})
    except httpx.HTTPError as exc:
        logger.warning("oauth2-proxy unreachable at %s: %s", settings.auth_internal_url, exc)
        return None

    if response.status_code not in (200, 202):
        return None

    headers = response.headers
    groups = tuple(g.strip() for g in headers.get("x-auth-request-groups", "").split(",") if g.strip())
    return User(
        username=headers.get("x-auth-request-user", ""),
        email=headers.get("x-auth-request-email", ""),
        groups=groups,
    )


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
