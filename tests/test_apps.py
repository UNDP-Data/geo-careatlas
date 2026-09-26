from pathlib import Path

import pytest

from careatlas.app.apps import AppConfigError, Role, Visibility, list_apps, load_app, visible_apps
from careatlas.app.auth import User

from helpers import write_app

ALICE = User(username="Alice", email="alice@undp.org", groups=("UNDP-Data", "UNDP-Data:geohub"))
BOB = User(username="bob", email="bob@example.org")


@pytest.fixture
def content(tmp_path: Path) -> Path:
    write_app(tmp_path, "open", 'title = "Open"\nvisibility = "public"\n[members]\nowners = ["alice"]\n')
    write_app(
        tmp_path,
        "closed",
        'title = "Closed"\nvisibility = "restricted"\n'
        '[members]\nowners = ["carol"]\neditors = ["@UNDP-Data/geohub"]\nviewers = ["bob"]\n',
    )
    return tmp_path


def test_owner_matches_login_case_insensitively(content):
    assert load_app(content, "open").role_for(ALICE) is Role.OWNER


def test_team_membership_grants_role(content):
    assert load_app(content, "closed").role_for(ALICE) is Role.EDITOR


def test_highest_role_wins(tmp_path):
    write_app(tmp_path, "both", '[members]\nowners = ["alice"]\nviewers = ["@UNDP-Data"]\n')
    assert load_app(tmp_path, "both").role_for(ALICE) is Role.OWNER


def test_public_app_is_viewable_by_anyone(content):
    app = load_app(content, "open")
    assert app.role_for(None) is Role.VIEWER
    assert app.role_for(BOB) is Role.VIEWER
    assert app.member_role(BOB) is None


def test_restricted_app_requires_membership(content):
    app = load_app(content, "closed")
    assert app.role_for(None) is None
    assert app.role_for(BOB) is Role.VIEWER
    assert app.role_for(User(username="mallory", email="m@example.org")) is None


def test_visibility_defaults_to_restricted(tmp_path):
    write_app(tmp_path, "plain", 'title = "Plain"\n')
    assert load_app(tmp_path, "plain").visibility is Visibility.RESTRICTED


def test_invalid_config_raises_and_is_skipped_in_listing(content):
    write_app(content, "broken", 'visibility = "secret"\n')
    with pytest.raises(AppConfigError):
        load_app(content, "broken")
    assert [a.slug for a in list_apps(content)] == ["closed", "open"]


def test_unsafe_slugs_are_rejected(content):
    assert load_app(content, "../closed") is None
    assert load_app(content, "Closed") is None


def test_visible_apps_filters_by_role(content):
    assert [a.slug for a, _ in visible_apps(content, None)] == ["open"]
    assert [(a.slug, r) for a, r in visible_apps(content, ALICE)] == [("closed", Role.EDITOR), ("open", Role.OWNER)]


def test_notebooks_skip_private_modules(tmp_path):
    write_app(tmp_path, "nb", "", notebooks=("a.py", "_helpers.py", "sub/b.py", "sub/__init__.py"))
    assert [n.name for n in load_app(tmp_path, "nb").notebooks()] == ["a", "sub/b"]
    assert load_app(tmp_path, "nb").notebooks()[0].description == "A notebook."


@pytest.mark.parametrize(("source", "title"), [
    ('import marimo\n@app.cell\ndef _(mo):\n    mo.md("# Care survey 2023")\n', "Care survey 2023"),
    ('@app.cell\ndef _(mo):\n    mo.md(r"""\n    Intro text\n\n    ## Results ##\n    """)\n', "Results"),
    ('@app.cell\ndef a(mo):\n    mo.md("# First")\n@app.cell\ndef b(mo):\n    mo.md("# Second")\n', "First"),
    ("x = 1\n", "Some notebook"),
    ("def (:\n", "Some notebook"),
])
def test_notebook_title_comes_from_its_first_heading(tmp_path, source, title):
    path = tmp_path / "some_notebook.py"
    path.write_text(source)
    from careatlas.app.apps import Notebook
    assert Notebook(name="some_notebook", path=path).title == title


def test_draft_apps_are_only_visible_to_owners_and_editors(tmp_path):
    write_app(
        tmp_path, "draft",
        'visibility = "public"\n[members]\nowners = ["carol"]\neditors = ["alice"]\nviewers = ["bob"]\n',
        notebooks=(),
    )
    app = load_app(tmp_path, "draft")
    assert app.is_draft
    assert app.role_for(None) is None
    assert app.role_for(BOB) is None
    assert app.role_for(ALICE) is Role.EDITOR
    assert app.role_for(User(username="carol", email="c@undp.org")) is Role.OWNER
    assert [a.slug for a, _ in visible_apps(tmp_path, BOB)] == []
    assert [a.slug for a, _ in visible_apps(tmp_path, ALICE)] == ["draft"]


def test_an_app_stops_being_a_draft_once_it_has_a_notebook(tmp_path):
    folder = write_app(tmp_path, "draft", 'visibility = "public"\n', notebooks=())
    assert load_app(tmp_path, "draft").role_for(None) is None
    (folder / "main.py").write_text("import marimo\n")
    app = load_app(tmp_path, "draft")
    assert not app.is_draft
    assert app.role_for(None) is Role.VIEWER
