import dataclasses

import pytest
from starlette.exceptions import HTTPException

from careatlas.app import auth, runner
from careatlas.app.auth import User
from careatlas.app.config import settings

from helpers import write_app

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def content(tmp_path, monkeypatch):
    write_app(tmp_path, "open", 'visibility = "public"\n')
    write_app(tmp_path, "closed", 'visibility = "restricted"\n[members]\nviewers = ["bob"]\n')
    patched = dataclasses.replace(
        settings,
        content_dir=tmp_path,
        auth_internal_url="http://auth.test/oauth2",
        auth_public_url="http://auth.test/oauth2",
        public_url="http://careatlas.test",
    )
    monkeypatch.setattr(runner, "settings", patched)
    monkeypatch.setattr(auth, "settings", patched)
    return tmp_path


def scope(path: str, kind: str = "http") -> dict:
    return {"type": kind, "path": path, "headers": [], "query_string": b"", "server": ("careatlas.test", 80), "scheme": "http"}


def signed_in_as(monkeypatch, user):
    async def fake_get_user(_connection):
        return user

    monkeypatch.setattr(runner, "get_user", fake_get_user)


async def test_public_app_is_served_without_sign_in(content, monkeypatch):
    signed_in_as(monkeypatch, None)
    assert await runner.authorize("open/main/", scope("/run/open/main/"))


async def test_unknown_app_is_not_found(content, monkeypatch):
    signed_in_as(monkeypatch, None)
    assert not await runner.authorize("missing/main/", scope("/run/missing/main/"))


async def test_restricted_app_redirects_anonymous_visitors_to_sign_in(content, monkeypatch):
    signed_in_as(monkeypatch, None)
    with pytest.raises(HTTPException) as exc:
        await runner.authorize("closed/main/", scope("/run/closed/main/"))
    assert exc.value.status_code == 303
    assert exc.value.headers["location"] == "http://auth.test/oauth2/start?rd=http%3A%2F%2Fcareatlas.test%2Frun%2Fclosed%2Fmain%2F"


async def test_restricted_app_is_hidden_from_non_members(content, monkeypatch):
    signed_in_as(monkeypatch, User(username="mallory", email="m@example.org"))
    assert not await runner.authorize("closed/main/", scope("/run/closed/main/"))
    assert not await runner.authorize("closed/main/ws", scope("/run/closed/main/ws", kind="websocket"))


async def test_restricted_app_allows_members(content, monkeypatch):
    signed_in_as(monkeypatch, User(username="Bob", email="bob@example.org"))
    assert await runner.authorize("closed/main/", scope("/run/closed/main/"))


@pytest.mark.parametrize("path", ["open/../closed/main/", "open/./x", "open/..\\closed/main"])
async def test_path_traversal_out_of_an_app_is_rejected(content, monkeypatch, path):
    signed_in_as(monkeypatch, None)
    assert not await runner.authorize(path, scope(f"/run/{path}"))


async def test_archive_is_never_served(content, monkeypatch):
    signed_in_as(monkeypatch, None)
    (content / "_archive" / "open-20260101-000000").mkdir(parents=True)
    assert not await runner.authorize("_archive/open-20260101-000000/main/", scope("/run/_archive/open-20260101-000000/main/"))
