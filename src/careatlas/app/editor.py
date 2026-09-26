"""Notebook editor sessions and the proxy in front of them.

Each editor gets their own ``marimo edit`` server for an app, running on a
local port against the app folder in their worktree (see ``content.py``). The
browser reaches it only through ``/edit/<session>/``, where every HTTP request
and websocket is checked: the session must belong to the signed-in user and
they must still be an editor or owner of the app.

marimo saves edits to the worktree as the user works; nothing is committed or
visible to others until they use the commit or publish actions.

Notebooks run arbitrary Python on the server. The editor processes get an
environment without the server's secrets, but anyone with the editor role can
still read files the server process can read.
"""

import asyncio
import logging
import os
import secrets
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import tomlkit
from starlette.requests import HTTPConnection
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed

from careatlas.app.apps import Role, load_app
from careatlas.app.auth import SESSION_COOKIE_PREFIX, User, get_user
from careatlas.app.config import settings
from careatlas.app.content import store, user_key

logger = logging.getLogger(__name__)

EDIT_PREFIX = "/edit"
STARTUP_TIMEOUT = 30.0
# Environment variables notebooks must not see.
SECRET_ENV = ("GITHUB_PAT_TOKEN", "NICEGUI_STORAGE_SECRET", "OAUTH_CLIENT_SECRET", "OAUTH_COOKIE_KEY")
# With these set, marimo treats CareAtlas as the uv project and installs packages with
# "uv add", which would edit CareAtlas's pyproject.toml and uv.lock. Without them it
# uses "uv pip install" into the notebooks' environment.
UV_PROJECT_ENV = ("UV", "UV_PROJECT_ENVIRONMENT")
# marimo's "Re-run all cells" has no default shortcut. Each user's editor settings bind it
# to this key combination, which the CareAtlas toolbar's "Run all" button sends to the editor.
RUN_ALL_HOTKEY = "Alt-Shift-r"
HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
              "transfer-encoding", "upgrade", "host", "content-length"}


@dataclass
class EditSession:
    id: str
    user: str
    app: str
    port: int
    folder: Path
    process: subprocess.Popen
    last_activity: float = field(default_factory=time.monotonic)

    @property
    def base_url(self) -> str:
        return f"{EDIT_PREFIX}/{self.id}"

    @property
    def alive(self) -> bool:
        return self.process.poll() is None

    def url(self, notebook: str | None = None) -> str:
        return f"{self.base_url}/" + (f"?file={notebook}.py" if notebook else "")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def notebook_env() -> dict[str, str]:
    """Environment for processes that handle notebook code: the server's, without its secrets."""
    env = {k: v for k, v in os.environ.items()
           if k not in SECRET_ENV and k not in UV_PROJECT_ENV and not k.startswith("AWS_")}
    env["MARIMO_SKIP_UPDATE_CHECK"] = "1"
    return env


def prepare_user_settings(user_dir: Path) -> Path:
    """Set up the user's marimo settings for CareAtlas.

    - Bind "Re-run all cells" for the toolbar's Run all button.
    - Install missing packages with uv: the notebooks' environment is created by uv and
      has no pip, so marimo's default installer fails. Packages installed this way go
      into the environment shared by all notebooks and are lost when it is rebuilt;
      anything a published notebook needs belongs in CareAtlas's pyproject.toml.

    marimo looks for .marimo.toml in the notebook's folder and its parents, so a file in
    <work>/<user>/ applies to all of that user's editor sessions and is never committed
    (it is outside every worktree). Other settings the user changes in marimo are kept.
    """
    path = user_dir / ".marimo.toml"
    document = tomlkit.parse(path.read_text(encoding="utf-8")) if path.is_file() else tomlkit.document()
    before = tomlkit.dumps(document)
    overrides = document.setdefault("keymap", tomlkit.table()).setdefault("overrides", tomlkit.table())
    overrides["global.runAll"] = RUN_ALL_HOTKEY
    packages = document.setdefault("package_management", tomlkit.table())
    if packages.get("manager", "pip") == "pip":
        packages["manager"] = "uv"
    if tomlkit.dumps(document) != before:
        path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


class EditorManager:
    def __init__(self) -> None:
        self._sessions: dict[str, EditSession] = {}
        self._lock = asyncio.Lock()

    def get(self, session_id: str) -> EditSession | None:
        session = self._sessions.get(session_id)
        return session if session and session.alive else None

    def find(self, user: User, app: str) -> EditSession | None:
        key = user_key(user)
        return next((s for s in self._sessions.values() if s.user == key and s.app == app and s.alive), None)

    async def open(self, user: User, app: str) -> EditSession:
        """Return the user's running session for the app, starting one if needed."""
        async with self._lock:
            existing = self.find(user, app)
            if existing:
                return existing
            folder = await asyncio.to_thread(store.workspace, app, user_key(user))
            session = await asyncio.to_thread(self._start, user_key(user), app, folder)
            self._sessions[session.id] = session
            logger.info("Started editor %s for %s on %s", session.id, session.user, app)
            return session

    def _start(self, user: str, app: str, folder: Path) -> EditSession:
        prepare_user_settings(folder.parent.parent)
        session_id = secrets.token_urlsafe(16)
        port = _free_port()
        command = [
            sys.executable, "-m", "marimo", "edit", str(folder),
            "--headless", "--no-token", "--skip-update-check",
            "--host", "127.0.0.1", "--port", str(port),
            "--base-url", f"{EDIT_PREFIX}/{session_id}",
            "--timeout", str(settings.edit_idle_minutes),
            "--watch",
        ]
        process = subprocess.Popen(
            command, cwd=folder, env=notebook_env(),
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        deadline = time.monotonic() + STARTUP_TIMEOUT
        health = f"http://127.0.0.1:{port}{EDIT_PREFIX}/{session_id}/health"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                error = (process.stderr.read() or "").strip().splitlines()
                raise RuntimeError(f"Editor failed to start: {error[-1] if error else process.returncode}")
            try:
                if httpx.get(health, timeout=1).status_code < 500:
                    return EditSession(id=session_id, user=user, app=app, port=port, folder=folder, process=process)
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        process.kill()
        raise RuntimeError("Editor did not start in time")

    def stop(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session and session.alive:
            session.process.terminate()
            try:
                session.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                session.process.kill()

    def stop_all(self) -> None:
        for session_id in list(self._sessions):
            self.stop(session_id)

    async def reap(self) -> None:
        """Forget sessions whose process exited, e.g. after marimo's idle timeout."""
        while True:
            await asyncio.sleep(60)
            for session_id, session in list(self._sessions.items()):
                if not session.alive:
                    self._sessions.pop(session_id, None)
                    logger.info("Editor %s for %s on %s has stopped", session_id, session.user, session.app)


editors = EditorManager()


# --- proxy ------------------------------------------------------------------

_http = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0))


async def _authorize(scope: Scope) -> EditSession | None:
    parts = scope["path"][len(EDIT_PREFIX) + 1:].split("/", 1)
    session = editors.get(parts[0]) if parts else None
    if session is None:
        return None
    user = await get_user(HTTPConnection(scope))
    if user is None or user_key(user) != session.user:
        return None
    app = await asyncio.to_thread(load_app, settings.content_dir, session.app)
    role = app.role_for(user) if app else None
    if role is None or role < Role.EDITOR:
        return None
    session.last_activity = time.monotonic()
    return session


def _upstream_headers(scope: Scope, session: EditSession) -> list[tuple[str, str]]:
    headers = []
    for raw_name, raw_value in scope["headers"]:
        name, value = raw_name.decode("latin-1").lower(), raw_value.decode("latin-1")
        if name in HOP_BY_HOP or name.startswith("sec-websocket") or name.startswith("x-forwarded"):
            continue
        if name == "cookie":
            # The sign-in session cookie stays with CareAtlas; notebooks never see it.
            value = "; ".join(
                part.strip() for part in value.split(";")
                if not part.strip().startswith(SESSION_COOKIE_PREFIX)
            )
            if not value:
                continue
        if name == "origin":
            # marimo only accepts requests that appear to come from itself.
            value = f"http://127.0.0.1:{session.port}"
        headers.append((name, value))
    headers.append(("host", f"127.0.0.1:{session.port}"))
    return headers


async def _proxy_http(scope: Scope, receive: Receive, send: Send, session: EditSession) -> None:
    body = b""
    while True:
        message = await receive()
        body += message.get("body", b"")
        if not message.get("more_body"):
            break
    query = scope.get("query_string", b"").decode("latin-1")
    url = f"http://127.0.0.1:{session.port}{scope['path']}" + (f"?{query}" if query else "")
    request = _http.build_request(scope["method"], url, headers=_upstream_headers(scope, session), content=body)
    try:
        response = await _http.send(request, stream=True)
    except httpx.HTTPError:
        await _plain(send, 502, b"The editor is not responding. Reopen it from the app page.")
        return
    try:
        headers = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in response.headers.multi_items()
                   if k.lower() not in HOP_BY_HOP]
        await send({"type": "http.response.start", "status": response.status_code, "headers": headers})
        async for chunk in response.aiter_raw():
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b""})
    finally:
        await response.aclose()


async def _proxy_websocket(scope: Scope, receive: Receive, send: Send, session: EditSession) -> None:
    client = WebSocket(scope, receive, send)
    query = scope.get("query_string", b"").decode("latin-1")
    url = f"ws://127.0.0.1:{session.port}{scope['path']}" + (f"?{query}" if query else "")
    headers = [(k, v) for k, v in _upstream_headers(scope, session) if k not in ("host", "origin")]
    try:
        upstream = await ws_connect(
            url, additional_headers=headers, origin=f"http://127.0.0.1:{session.port}",
            proxy=None, max_size=None, compression=None,
        )
    except (OSError, ConnectionClosed, Exception):
        await client.close(code=1011)
        return
    await client.accept()

    async def browser_to_editor() -> None:
        try:
            while True:
                message = await client.receive()
                if message["type"] == "websocket.disconnect":
                    break
                data = message.get("text") if message.get("text") is not None else message.get("bytes")
                await upstream.send(data)
        except (WebSocketDisconnect, ConnectionClosed):
            pass

    async def editor_to_browser() -> None:
        try:
            async for data in upstream:
                if isinstance(data, str):
                    await client.send_text(data)
                else:
                    await client.send_bytes(data)
        except (WebSocketDisconnect, ConnectionClosed, RuntimeError):
            pass

    tasks = [asyncio.create_task(browser_to_editor()), asyncio.create_task(editor_to_browser())]
    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in tasks:
        task.cancel()
    await upstream.close()
    try:
        await client.close()
    except RuntimeError:
        pass


async def _plain(send: Send, status: int, body: bytes) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")]})
    await send({"type": "http.response.body", "body": body})


async def edit_proxy(scope: Scope, receive: Receive, send: Send) -> None:
    """ASGI app mounted at /edit."""
    if scope["type"] not in ("http", "websocket"):
        return
    # Mounting moves the prefix into root_path; the editor expects the full path.
    if not scope["path"].startswith(f"{EDIT_PREFIX}/"):
        scope = {**scope, "path": f"{EDIT_PREFIX}{scope['path']}", "root_path": ""}

    session = await _authorize(scope)
    if session is None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4404})
        else:
            await _plain(send, 404, b"This editor session does not exist or is not yours.")
        return

    if scope["type"] == "websocket":
        await _proxy_websocket(scope, receive, send, session)
    else:
        await _proxy_http(scope, receive, send, session)
