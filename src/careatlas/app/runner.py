"""Serves app notebooks read-only through marimo, enforcing each app's access rules.

A notebook is served at ``/run/<app>/<notebook>``. marimo calls ``authorize``
before every HTTP and websocket request under that prefix, including its
static assets, so restricted apps are never reachable without the viewer role.
"""

import logging

import marimo
from starlette.exceptions import HTTPException
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send

from careatlas.app.apps import AppConfigError, Visibility, load_app
from careatlas.app.auth import get_user, sign_in_url
from careatlas.app.config import settings

logger = logging.getLogger(__name__)

RUN_PREFIX = "/run"


def notebook_url(app_slug: str, notebook_name: str) -> str:
    return f"{RUN_PREFIX}/{app_slug}/{notebook_name}/"


async def authorize(app_path: str, scope: Scope) -> bool:
    """marimo validate callback. Returning False yields 404; raising HTTPException sets the status."""
    parts = app_path.split("/")
    # marimo resolves the path against the content directory, so "." and ".." could
    # escape the app checked here and reach another app's notebooks.
    if any(part in (".", "..") or "\\" in part for part in parts):
        return False

    try:
        app = load_app(settings.content_dir, parts[0])
    except AppConfigError as exc:
        logger.error("Refusing to serve %s: %s", parts[0], exc)
        return False
    if app is None:
        return False
    if app.visibility is Visibility.PUBLIC:
        return True

    connection = HTTPConnection(scope)
    user = await get_user(connection)
    if app.role_for(user) is not None:
        return True
    if user is None and settings.auth_enabled and scope["type"] == "http":
        raise HTTPException(status_code=303, headers={"location": sign_in_url(connection)})
    # Same response as an unknown app, so restricted apps are not disclosed to non-members.
    return False


def create_runner() -> ASGIApp:
    marimo_app = (
        marimo.create_asgi_app(quiet=True, skew_protection=True)
        .with_dynamic_directory(
            path=RUN_PREFIX,
            directory=str(settings.content_dir),
            validate_callback=authorize,
        )
        .build()
    )

    async def runner(scope: Scope, receive: Receive, send: Send) -> None:
        # Mounting moves the prefix into root_path, but marimo matches on the full path.
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if not path.startswith(f"{RUN_PREFIX}/"):
                scope["path"] = f"{RUN_PREFIX}{path}"
            scope["root_path"] = ""
        await marimo_app(scope, receive, send)

    return runner
