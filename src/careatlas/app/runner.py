"""Serves notebooks read-only through marimo, enforcing each app's access rules.

Published notebooks are served at ``/run/<app>/<notebook>``. Versions submitted
for review are served to the app's owners at
``/review/<app>/<editor>/<app>/<notebook>``, from a checkout of the submitted
commit. marimo calls the matching ``authorize`` function before every HTTP and
websocket request under each prefix, including its static assets.
"""

import logging

import marimo
from starlette.exceptions import HTTPException
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send

from careatlas.app.apps import AppConfigError, Role, Visibility, load_app
from careatlas.app.auth import get_user, sign_in_url
from careatlas.app.config import settings

logger = logging.getLogger(__name__)

RUN_PREFIX = "/run"
REVIEW_PREFIX = "/review"


def notebook_url(app_slug: str, notebook_name: str) -> str:
    return f"{RUN_PREFIX}/{app_slug}/{notebook_name}/"


def review_notebook_url(app_slug: str, editor: str, notebook_name: str) -> str:
    return f"{REVIEW_PREFIX}/{app_slug}/{editor}/{app_slug}/{notebook_name}/"


def _unsafe(parts: list[str]) -> bool:
    # marimo resolves the path against a directory on disk, so "." and ".." could
    # escape the app checked here and reach another app's notebooks.
    return any(part in (".", "..") or "\\" in part for part in parts)


async def authorize(app_path: str, scope: Scope) -> bool:
    """marimo validate callback. Returning False yields 404; raising HTTPException sets the status."""
    parts = app_path.split("/")
    if _unsafe(parts):
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


async def authorize_review(app_path: str, scope: Scope) -> bool:
    """Only owners of the app may run a submitted version, and only that app's notebooks in it."""
    parts = app_path.split("/")
    # <app>/<editor>/<app>/<notebook>: the checkout holds the whole repository, so the
    # notebook must be inside the reviewed app's own folder.
    if _unsafe(parts) or len(parts) < 4 or parts[2] != parts[0]:
        return False
    try:
        app = load_app(settings.content_dir, parts[0])
    except AppConfigError:
        return False
    if app is None:
        return False
    user = await get_user(HTTPConnection(scope))
    return app.role_for(user) is Role.OWNER


def _create(prefix: str, directory: str, validate) -> ASGIApp:
    marimo_app = (
        marimo.create_asgi_app(quiet=True, skew_protection=True)
        .with_dynamic_directory(path=prefix, directory=directory, validate_callback=validate)
        .build()
    )

    async def runner(scope: Scope, receive: Receive, send: Send) -> None:
        # Mounting moves the prefix into root_path, but marimo matches on the full path.
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if not path.startswith(f"{prefix}/"):
                scope["path"] = f"{prefix}{path}"
            scope["root_path"] = ""
        await marimo_app(scope, receive, send)

    return runner


def create_runner() -> ASGIApp:
    return _create(RUN_PREFIX, str(settings.content_dir), authorize)


def create_review_runner() -> ASGIApp:
    return _create(REVIEW_PREFIX, str(settings.data_dir / "reviews"), authorize_review)
