import ast
import dataclasses

import pytest

from careatlas.app.apps import AppConfigError, Role, Visibility, list_apps, load_app
from careatlas.app.auth import User
from careatlas.app.manage import (
    archive_app,
    archive_notebook,
    create_app,
    create_notebook,
    normalize_members,
    save_app,
    slugify,
)

ALICE = User(username="Alice", email="alice@undp.org")


def test_create_app_makes_creator_owner_with_starter_notebook(tmp_path):
    app = create_app(tmp_path, "care", "Care Economy", "About care.", Visibility.RESTRICTED, ALICE)
    loaded = load_app(tmp_path, "care")
    assert loaded == app
    assert loaded.role_for(ALICE) is Role.OWNER
    assert [n.name for n in loaded.notebooks()] == ["main"]


def test_created_notebook_is_valid_python_for_any_title(tmp_path):
    app = create_app(tmp_path, "care", 'Tricky """ \\ {title}', "", Visibility.PUBLIC, ALICE)
    notebook = create_notebook(app, "second", title='Ends with a backslash \\')
    for nb in load_app(tmp_path, "care").notebooks():
        ast.parse(nb.path.read_text())
    assert notebook.description == 'Ends with a backslash \\ notebook of Tricky """ \\ {title}.'


@pytest.mark.parametrize("slug", ["Care", "../care", "_hidden", "has space", ""])
def test_create_app_rejects_invalid_slugs(tmp_path, slug):
    with pytest.raises(AppConfigError):
        create_app(tmp_path, slug, "Title", "", Visibility.PUBLIC, ALICE)


def test_create_app_rejects_existing_slug(tmp_path):
    create_app(tmp_path, "care", "Care", "", Visibility.PUBLIC, ALICE)
    with pytest.raises(AppConfigError):
        create_app(tmp_path, "care", "Again", "", Visibility.PUBLIC, ALICE)


def test_save_round_trips_special_characters(tmp_path):
    app = create_app(tmp_path, "care", "Care", "", Visibility.PUBLIC, ALICE)
    save_app(dataclasses.replace(app, title='Quotes " and \\ backslash', description="Line one\nLine two"))
    loaded = load_app(tmp_path, "care")
    assert loaded.title == 'Quotes " and \\ backslash'
    assert loaded.description == "Line one\nLine two"


def test_save_requires_an_owner(tmp_path):
    app = create_app(tmp_path, "care", "Care", "", Visibility.PUBLIC, ALICE)
    with pytest.raises(AppConfigError):
        save_app(dataclasses.replace(app, owners=()))
    assert load_app(tmp_path, "care").owners == ("Alice",)


def test_members_are_validated_and_deduplicated():
    assert normalize_members([" bob ", "Bob", "@UNDP-Data/geohub", "@UNDP-Data", ""]) == (
        "bob",
        "@UNDP-Data/geohub",
        "@UNDP-Data",
    )
    for bad in ["bob smith", "bob/team", "@", "-bob", "a" * 40]:
        with pytest.raises(AppConfigError):
            normalize_members([bad])


def test_archived_app_is_no_longer_listed_or_loadable(tmp_path):
    app = create_app(tmp_path, "care", "Care", "", Visibility.PUBLIC, ALICE)
    target = archive_app(tmp_path, app)
    assert target.parent == tmp_path / "_archive"
    assert (target / "app.toml").is_file()
    assert list_apps(tmp_path) == []
    assert load_app(tmp_path, "_archive") is None


def test_archived_notebook_moves_out_of_the_app(tmp_path):
    app = create_app(tmp_path, "care", "Care", "", Visibility.PUBLIC, ALICE)
    extra = create_notebook(app, "extra")
    target = archive_notebook(tmp_path, app, extra)
    assert target.parent == tmp_path / "_archive" / "care"
    assert [n.name for n in load_app(tmp_path, "care").notebooks()] == ["main"]


def test_slugify():
    assert slugify("Care Economy 2025!") == "care_economy_2025"



def test_expired_archive_entries_use_the_archive_date(tmp_path):
    from datetime import datetime, timezone

    from careatlas.app.manage import expired_archive_entries, remove_expired_archive

    archive = tmp_path / "_archive"
    (archive / "old_app-20260101-120000").mkdir(parents=True)
    (archive / "new_app-20260920-120000").mkdir()
    (archive / "care").mkdir()
    (archive / "care" / "old_notebook-20260201-000000.py").write_text("")
    (archive / "care" / "new_notebook-20260920-000000.py").write_text("")
    (archive / "unrecognised").mkdir()
    now = datetime(2026, 9, 25, tzinfo=timezone.utc)

    expired = expired_archive_entries(tmp_path, 30, now)
    assert [p.name for p in expired] == ["old_app-20260101-120000", "old_notebook-20260201-000000.py"]
    assert expired_archive_entries(tmp_path, 0, now) == []

    assert remove_expired_archive(tmp_path, 30, now) == [
        "_archive/old_app-20260101-120000",
        "_archive/care/old_notebook-20260201-000000.py",
    ]
    assert sorted(p.name for p in archive.iterdir()) == ["care", "new_app-20260920-120000", "unrecognised"]


def test_folder_emptied_by_removal_is_deleted(tmp_path):
    from datetime import datetime, timezone

    from careatlas.app.manage import remove_expired_archive

    (tmp_path / "_archive" / "care").mkdir(parents=True)
    (tmp_path / "_archive" / "care" / "nb-20260101-000000.py").write_text("")
    remove_expired_archive(tmp_path, 30, datetime(2026, 9, 25, tzinfo=timezone.utc))
    assert not (tmp_path / "_archive" / "care").exists()
