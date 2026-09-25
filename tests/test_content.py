import subprocess
from pathlib import Path

import pytest

from careatlas.app.content import Author, ContentStore, GitError, MergeConflict

ALICE = Author("alice", "alice@undp.org")
OWNER = Author("olivia", "olivia@undp.org")
APP_TOML = 'title = "Care"\nvisibility = "public"\n[members]\nowners = ["olivia"]\neditors = ["alice"]\n'


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    """An empty bare repository standing in for GitHub."""
    path = tmp_path / "remote.git"
    git("init", "--bare", "--quiet", "--initial-branch=main", str(path), cwd=tmp_path)
    return path


@pytest.fixture
def store(tmp_path: Path, remote: Path) -> ContentStore:
    store = ContentStore(tmp_path / "data", remote=str(remote))
    store.ensure()

    def add_app(tree: Path) -> None:
        (tree / "care").mkdir()
        (tree / "care" / "app.toml").write_text(APP_TOML)
        (tree / "care" / "main.py").write_text("x = 1\n")

    store.change_main("Add care app", OWNER, add_app)
    return store


def remote_file(remote: Path, ref: str, path: str) -> str:
    return git("--git-dir", str(remote), "show", f"{ref}:{path}", cwd=remote.parent)


def test_ensure_initialises_an_empty_remote(tmp_path, remote):
    store = ContentStore(tmp_path / "data", remote=str(remote))
    store.ensure()
    assert (store.published / "README.md").is_file()
    assert "CareAtlas" in remote_file(remote, "main", "README.md")


def test_local_mode_seeds_sample_apps(tmp_path):
    seed = tmp_path / "seed"
    (seed / "demo").mkdir(parents=True)
    (seed / "demo" / "app.toml").write_text('title = "Demo"\n')
    (seed / "not_an_app").mkdir()
    store = ContentStore(tmp_path / "data", seed_dir=seed)
    store.ensure()
    assert (store.published / "demo" / "app.toml").is_file()
    assert not (store.published / "not_an_app").exists()


def test_owner_changes_are_published_and_pushed(store, remote):
    assert (store.published / "care" / "main.py").read_text() == "x = 1\n"
    assert remote_file(remote, "main", "care/main.py") == "x = 1"


def test_edits_stay_private_until_committed(store, remote):
    notebook = store.workspace("care", "alice") / "main.py"
    notebook.write_text("x = 2\n")
    status = store.status("care", "alice")
    assert status.changed == ("care/main.py",)
    assert (store.published / "care" / "main.py").read_text() == "x = 1\n"
    assert "edit/care/alice" not in git("--git-dir", str(remote), "branch", cwd=remote.parent)

    store.commit("care", "alice", "Change x", ALICE)
    assert remote_file(remote, "edit/care/alice", "care/main.py") == "x = 2"
    assert store.status("care", "alice").ahead == 1
    # Still not published
    assert (store.published / "care" / "main.py").read_text() == "x = 1\n"


def test_commit_never_includes_app_toml(store):
    folder = store.workspace("care", "alice")
    (folder / "app.toml").write_text(APP_TOML.replace('editors = ["alice"]', 'owners = ["alice"]'))
    assert store.commit("care", "alice", "Promote myself", ALICE) is None


def test_discard_removes_uncommitted_changes(store):
    folder = store.workspace("care", "alice")
    (folder / "main.py").write_text("broken\n")
    (folder / "new.py").write_text("y = 1\n")
    store.discard("care", "alice")
    assert (folder / "main.py").read_text() == "x = 1\n"
    assert not (folder / "new.py").exists()
    assert not store.status("care", "alice").dirty


def test_review_and_approve_publishes_the_submitted_version(store, remote):
    folder = store.workspace("care", "alice")
    (folder / "main.py").write_text("x = 2\n")
    store.commit("care", "alice", "Change x", ALICE)
    review = store.submit_review("care", "alice")
    assert review.files == ("care/main.py",)

    # Later commits are not part of the submitted review
    (folder / "main.py").write_text("x = 3\n")
    store.commit("care", "alice", "Change x again", ALICE)

    [pending] = store.reviews("care")
    assert "+x = 2" in store.review_diff(pending)
    store.approve(pending, OWNER, "Change x to 2")
    assert (store.published / "care" / "main.py").read_text() == "x = 2\n"
    assert remote_file(remote, "main", "care/main.py") == "x = 2"
    assert store.reviews("care") == []


def test_owner_publishes_directly(store):
    folder = store.workspace("care", "olivia")
    (folder / "main.py").write_text("x = 5\n")
    store.publish_workspace("care", "olivia", "Set x to 5", OWNER)
    assert (store.published / "care" / "main.py").read_text() == "x = 5\n"
    status = store.status("care", "olivia")
    assert (status.ahead, status.behind) == (0, 0)


def test_conflicting_changes_are_reported_and_leave_branches_intact(store):
    alice = store.workspace("care", "alice")
    olivia = store.workspace("care", "olivia")
    (alice / "main.py").write_text("x = 'alice'\n")
    store.commit("care", "alice", "Alice's change", ALICE)
    review = store.submit_review("care", "alice")
    (olivia / "main.py").write_text("x = 'olivia'\n")
    store.publish_workspace("care", "olivia", "Olivia's change", OWNER)

    with pytest.raises(MergeConflict) as exc:
        store.approve(review, OWNER, "Publish reviewed change")
    assert exc.value.files == ["care/main.py"]
    assert (store.published / "care" / "main.py").read_text() == "x = 'olivia'\n"

    with pytest.raises(MergeConflict):
        store.update_from_main("care", "alice", ALICE)
    assert (alice / "main.py").read_text() == "x = 'alice'\n"
    assert not store.status("care", "alice").dirty


def test_update_from_main_brings_in_published_changes(store):
    alice = store.workspace("care", "alice")
    olivia = store.workspace("care", "olivia")
    (olivia / "extra.py").write_text("z = 1\n")
    store.publish_workspace("care", "olivia", "Add extra", OWNER)
    assert store.status("care", "alice").behind > 0
    store.update_from_main("care", "alice", ALICE)
    assert (alice / "extra.py").is_file()
    assert store.status("care", "alice").behind == 0


def test_publishing_refuses_changes_outside_the_app(store):
    tree = store.workspace("care", "alice").parent
    (tree / "care" / "main.py").write_text("x = 2\n")
    (tree / "other").mkdir()
    (tree / "other" / "sneaky.py").write_text("")
    git("add", "--all", cwd=tree)
    git("-c", "user.name=a", "-c", "user.email=a@b", "commit", "-qm", "sneaky", cwd=tree)
    review = store.submit_review("care", "alice")
    with pytest.raises(GitError, match="outside this app"):
        store.approve(review, OWNER, "Publish reviewed change")
    assert not (store.published / "other").exists()


def test_workspace_is_restored_from_the_remote_after_storage_loss(tmp_path, store, remote):
    (store.workspace("care", "alice") / "main.py").write_text("x = 9\n")
    store.commit("care", "alice", "Change", ALICE)

    fresh = ContentStore(tmp_path / "new-data", remote=str(remote))
    fresh.ensure()
    assert (fresh.workspace("care", "alice") / "main.py").read_text() == "x = 9\n"


def test_names_are_validated(store):
    with pytest.raises(GitError):
        store.workspace("../care", "alice")
    with pytest.raises(GitError):
        store.workspace("care", "../alice")


@pytest.mark.parametrize(("prefer", "expected"), [("mine", "x = 'alice'\n"), ("published", "x = 'olivia'\n")])
def test_conflicts_can_be_resolved_by_choosing_a_side(store, prefer, expected):
    alice = store.workspace("care", "alice")
    olivia = store.workspace("care", "olivia")
    (alice / "main.py").write_text("x = 'alice'\n")
    (alice / "extra.py").write_text("mine = True\n")
    store.commit("care", "alice", "Alice's change", ALICE)
    (olivia / "main.py").write_text("x = 'olivia'\n")
    (olivia / "other.py").write_text("theirs = True\n")
    store.publish_workspace("care", "olivia", "Olivia's change", OWNER)

    store.update_from_main("care", "alice", ALICE, prefer=prefer)
    assert (alice / "main.py").read_text() == expected
    assert (alice / "extra.py").is_file() and (alice / "other.py").is_file()
    assert store.status("care", "alice").behind == 0

    review = store.submit_review("care", "alice")
    store.approve(review, OWNER, "Publish reviewed change")
    assert (store.published / "care" / "main.py").read_text() == expected


def test_changes_to_other_apps_do_not_mark_a_workspace_behind(store):
    store.workspace("care", "alice")

    def add_other_app(tree):
        (tree / "other").mkdir()
        (tree / "other" / "app.toml").write_text('title = "Other"\n')

    store.change_main("Add other app", OWNER, add_other_app)
    assert store.status("care", "alice").behind == 0


def test_unreachable_repository_gives_a_readable_error(tmp_path):
    store = ContentStore(tmp_path / "data", remote=str(tmp_path / "missing.git"))
    with pytest.raises(GitError, match="content repository is not available"):
        store.change_main("Anything", OWNER, lambda tree: None)


def test_caches_are_never_committed(tmp_path, remote):
    store = ContentStore(tmp_path / "data", remote=str(remote))
    store.ensure()
    (store.published / ".gitignore").unlink(missing_ok=True)

    def add_app(tree):
        (tree / "care").mkdir()
        (tree / "care" / "app.toml").write_text(APP_TOML)
        (tree / "care" / "__marimo__").mkdir()
        (tree / "care" / "__marimo__" / "session.json").write_text("{}")

    store.change_main("Add app", OWNER, add_app)
    assert not (store.published / "care" / "__marimo__").exists()


def test_publishing_squashes_into_one_commit_with_the_confirmed_message(store, remote):
    folder = store.workspace("care", "alice")
    for value in (2, 3):
        (folder / "main.py").write_text(f"x = {value}\n")
        store.commit("care", "alice", f"Set x to {value} for now", ALICE)
    review = store.submit_review("care", "alice")
    assert store.review_messages(review) == ["Set x to 2 for now", "Set x to 3 for now"]

    store.approve(review, OWNER, "Update x to its final value")
    log = git("--git-dir", str(remote), "log", "--format=%an|%s|%b", "main", cwd=remote.parent).splitlines()
    assert log[0] == "alice|Update x to its final value|Approved-by: olivia <olivia@undp.org>"
    assert "Set x to" not in "\n".join(log)
    # The editor's branch starts again from main, so its interim messages are gone too
    assert git("--git-dir", str(remote), "rev-parse", "edit/care/alice", cwd=remote.parent) == \
        git("--git-dir", str(remote), "rev-parse", "main", cwd=remote.parent)
    status = store.status("care", "alice")
    assert (status.ahead, status.behind) == (0, 0)


def test_later_work_survives_approval_of_an_earlier_submission(store):
    folder = store.workspace("care", "alice")
    (folder / "main.py").write_text("x = 2\n")
    store.commit("care", "alice", "Set x to two", ALICE)
    review = store.submit_review("care", "alice")
    (folder / "extra.py").write_text("y = 1\n")
    store.commit("care", "alice", "Add extra notebook", ALICE)

    store.approve(review, OWNER, "Set x to two")
    assert (folder / "extra.py").is_file()
    store.update_from_main("care", "alice", ALICE)
    status = store.status("care", "alice")
    assert (status.ahead, status.behind) == (1, 0)


def test_expired_archive_is_removed_from_main_but_kept_in_history(store, remote):
    def archive_old_app(tree):
        (tree / "_archive" / "gone-20200101-000000").mkdir(parents=True)
        (tree / "_archive" / "gone-20200101-000000" / "app.toml").write_text('title = "Gone"\n')

    store.change_main("Archive app gone", OWNER, archive_old_app)
    assert store.remove_expired_archive(30) == ["_archive/gone-20200101-000000"]
    assert not (store.published / "_archive").exists()

    subject = git("--git-dir", str(remote), "log", "-1", "--format=%an|%s", "main", cwd=remote.parent)
    assert subject == "CareAtlas|Remove archived items older than 30 days"
    assert remote_file(remote, "main~1", "_archive/gone-20200101-000000/app.toml") == 'title = "Gone"'


def test_nothing_is_committed_when_nothing_expired(store, remote):
    before = git("--git-dir", str(remote), "rev-parse", "main", cwd=remote.parent)
    assert store.remove_expired_archive(30) == []
    assert git("--git-dir", str(remote), "rev-parse", "main", cwd=remote.parent) == before
