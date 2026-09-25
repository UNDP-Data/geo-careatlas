"""Git storage for app content.

The server keeps a bare clone of the content repository and checks it out into
worktrees that share its object store::

    <data_dir>/
      repo.git/                 bare clone; remote "origin" is CONTENT_REPO
      published/                detached worktree at main: what viewers see
      work/<user>/<app>/        worktree on branch edit/<app>/<user>: one editor's copy
      tmp/                      short-lived worktrees used to build commits on main

Editors change files in their own worktree; nothing leaves it until they
commit, which commits the app's folder and pushes their branch. Publishing
merges a branch into main in a temporary worktree, pushes main and then moves
the published worktree to it, so viewers never see a half-finished merge.

All operations are blocking; call them from a worker thread. A single lock
serialises them, which is enough for one server process.
"""

import base64
import logging
import os
import re
import shutil
import subprocess
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from careatlas.app.apps import APP_FILE, SLUG_PATTERN
from careatlas.app.auth import User
from careatlas.app.config import SAMPLE_CONTENT_DIR, settings
from careatlas.app.manage import expired_archive_entries, remove_expired_archive

logger = logging.getLogger(__name__)

MAIN = "main"
REVIEW_REFS = "refs/careatlas/review"
BOT_NAME = "CareAtlas"
BOT_EMAIL = "careatlas@undp.org"
USER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")

REPO_README = """# CareAtlas notebooks

Content for [CareAtlas](https://github.com/UNDP-Data/geo-careatlas). Each folder
is an app: an `app.toml` with its title, visibility and members, and one or more
marimo notebooks. Changes are normally made through CareAtlas.
"""

REPO_GITIGNORE = """__pycache__/
__marimo__/
.ipynb_checkpoints/
.DS_Store
"""


class GitError(RuntimeError):
    """A git command failed. The message is safe to show to users."""


class MergeConflict(GitError):
    def __init__(self, files: list[str]) -> None:
        super().__init__("Conflicting changes in: " + ", ".join(files))
        self.files = files


@dataclass(frozen=True)
class Author:
    name: str
    email: str


@dataclass(frozen=True)
class WorkspaceStatus:
    # Uncommitted files in the app folder, relative to the repository root
    changed: tuple[str, ...]
    # Files in the app folder the editor committed that are not published yet
    ahead: int
    # Files in the app folder published since the editor's branch was last updated
    behind: int

    @property
    def dirty(self) -> bool:
        return bool(self.changed)


@dataclass(frozen=True)
class Review:
    app: str
    user: str
    commit: str
    files: tuple[str, ...]


class ContentStore:
    def __init__(self, data_dir: Path, remote: str = "", token: str | None = None,
                 seed_dir: Path | None = None) -> None:
        self.data_dir = data_dir
        self.remote = remote
        self.token = token
        self.seed_dir = seed_dir
        self.repo = data_dir / "repo.git"
        self.published = data_dir / "published"
        self.work_root = data_dir / "work"
        self.tmp_root = data_dir / "tmp"
        self._lock = threading.RLock()

    # --- git plumbing -----------------------------------------------------

    def _env(self, network: bool, author: Author | None) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.pop("GITHUB_PAT_TOKEN", None)
        env["GIT_TERMINAL_PROMPT"] = "0"
        if network and self.token:
            # Passed as configuration through the environment so the token never
            # appears in a command line, a remote URL or a file on disk.
            credentials = base64.b64encode(f"x-access-token:{self.token}".encode()).decode()
            env["GIT_CONFIG_COUNT"] = "1"
            env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
            env["GIT_CONFIG_VALUE_0"] = f"Authorization: Basic {credentials}"
        who = author or Author(BOT_NAME, BOT_EMAIL)
        env["GIT_AUTHOR_NAME"] = who.name
        env["GIT_AUTHOR_EMAIL"] = who.email
        env["GIT_COMMITTER_NAME"] = BOT_NAME
        env["GIT_COMMITTER_EMAIL"] = BOT_EMAIL
        return env

    def _git(self, *args: str, cwd: Path | None = None, network: bool = False,
             author: Author | None = None, check: bool = True) -> subprocess.CompletedProcess:
        location = ["-C", str(cwd)] if cwd else ["--git-dir", str(self.repo)]
        result = subprocess.run(
            ["git", *location, *args],
            env=self._env(network, author),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if check and result.returncode != 0:
            message = (result.stderr or result.stdout).strip().splitlines()
            raise GitError(f"git {args[0]} failed: {message[-1] if message else result.returncode}")
        return result

    def _out(self, *args: str, cwd: Path | None = None) -> str:
        return self._git(*args, cwd=cwd).stdout.strip()

    def _ref_exists(self, ref: str) -> bool:
        return self._git("rev-parse", "--verify", "--quiet", ref, check=False).returncode == 0

    # --- setup --------------------------------------------------------------

    @property
    def ready(self) -> bool:
        return (self.repo / "HEAD").exists() and (self.published / ".git").exists()

    def _require_ready(self) -> None:
        """Retry setup if startup failed (e.g. GitHub was unreachable), with a readable error."""
        if self.ready:
            return
        try:
            self.ensure()
        except GitError as exc:
            raise GitError(f"The content repository is not available: {exc}") from exc

    def ensure(self) -> None:
        """Clone or open the repository and check out the published worktree."""
        with self._lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            if not (self.repo / "HEAD").exists():
                if self.remote:
                    logger.info("Cloning content repository")
                    self._git("clone", "--bare", "--quiet", self.remote, str(self.repo),
                              cwd=self.data_dir, network=True)
                else:
                    self._git("init", "--bare", "--quiet", f"--initial-branch={MAIN}", str(self.repo),
                              cwd=self.data_dir)
            if self.remote:
                # Keep remote branches under origin/ so fetching never overwrites local branches.
                self._git("config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
            # Caches marimo and Python write next to notebooks never belong in commits, whether
            # or not the repository has its own .gitignore. This file applies to all worktrees.
            (self.repo / "info").mkdir(exist_ok=True)
            (self.repo / "info" / "exclude").write_text(REPO_GITIGNORE)
            self._git("worktree", "prune")
            self._fetch()

            if not self._ref_exists(f"refs/heads/{MAIN}"):
                if self._ref_exists(f"refs/remotes/origin/{MAIN}"):
                    self._git("branch", MAIN, f"refs/remotes/origin/{MAIN}")
                else:
                    self._create_initial_commit()

            self._fast_forward_main()
            if not (self.published / ".git").exists():
                shutil.rmtree(self.published, ignore_errors=True)
                self._git("worktree", "add", "--quiet", "--detach", str(self.published), MAIN)
            self._checkout_published()

    def _create_initial_commit(self) -> None:
        with self._temporary_worktree(orphan=True) as tree:
            (tree / "README.md").write_text(REPO_README)
            (tree / ".gitignore").write_text(REPO_GITIGNORE)
            if not self.remote and self.seed_dir and self.seed_dir.is_dir():
                for app_dir in sorted(self.seed_dir.iterdir()):
                    if (app_dir / APP_FILE).is_file() and SLUG_PATTERN.match(app_dir.name):
                        shutil.copytree(app_dir, tree / app_dir.name,
                                        ignore=shutil.ignore_patterns("__pycache__", "__init__.py"))
            self._git("add", "--all", cwd=tree)
            self._git("commit", "--quiet", "-m", "Initialise CareAtlas content", cwd=tree)
            self._git("update-ref", f"refs/heads/{MAIN}", self._out("rev-parse", "HEAD", cwd=tree))
        self._push(MAIN)

    def _fetch(self) -> None:
        if self.remote:
            self._git("fetch", "--quiet", "--prune", "origin", network=True)

    def _push(self, branch: str, force: bool = False) -> None:
        if self.remote:
            refspec = f"refs/heads/{branch}:refs/heads/{branch}"
            self._git("push", "--quiet", "origin", f"+{refspec}" if force else refspec, network=True)

    def _fast_forward_main(self) -> None:
        """Move main to origin/main when someone else pushed, as long as no history is lost."""
        remote_main = f"refs/remotes/origin/{MAIN}"
        if not self.remote or not self._ref_exists(remote_main):
            return
        local, remote = self._out("rev-parse", MAIN), self._out("rev-parse", remote_main)
        if local == remote:
            return
        if self._git("merge-base", "--is-ancestor", local, remote, check=False).returncode == 0:
            self._git("update-ref", f"refs/heads/{MAIN}", remote, local)
        elif self._git("merge-base", "--is-ancestor", remote, local, check=False).returncode != 0:
            logger.error("Local and remote main have diverged; not updating published content")

    def _checkout_published(self) -> None:
        self._git("checkout", "--quiet", "--force", "--detach", MAIN, cwd=self.published)
        self._git("clean", "--quiet", "-fd", cwd=self.published)

    def refresh(self) -> None:
        """Pick up changes pushed to the content repository from elsewhere."""
        with self._lock:
            self._require_ready()
            self._fetch()
            self._fast_forward_main()
            self._checkout_published()

    @contextmanager
    def _temporary_worktree(self, orphan: bool = False) -> Iterator[Path]:
        self.tmp_root.mkdir(parents=True, exist_ok=True)
        path = self.tmp_root / uuid.uuid4().hex
        if orphan:
            self._git("worktree", "add", "--quiet", "--orphan", "-b", f"tmp-{path.name}", str(path))
        else:
            self._git("worktree", "add", "--quiet", "--detach", str(path), MAIN)
        try:
            yield path
        finally:
            self._git("worktree", "remove", "--force", str(path), check=False)
            shutil.rmtree(path, ignore_errors=True)
            if orphan:
                self._git("branch", "-D", f"tmp-{path.name}", check=False)

    def _commit_to_main(self, tree: Path, message: str, author: Author) -> str | None:
        """Commit everything in a temporary worktree and publish it. Returns the new commit, if any."""
        self._git("add", "--all", cwd=tree)
        if self._git("diff", "--cached", "--quiet", cwd=tree, check=False).returncode == 0:
            return None
        self._git("commit", "--quiet", "-m", message, cwd=tree, author=author)
        return self._publish_head(tree)

    def _publish_head(self, tree: Path) -> str:
        new = self._out("rev-parse", "HEAD", cwd=tree)
        old = self._out("rev-parse", MAIN)
        self._git("update-ref", f"refs/heads/{MAIN}", new, old)
        try:
            self._push(MAIN)
        except GitError:
            # Keep local main identical to what the remote accepted.
            self._git("update-ref", f"refs/heads/{MAIN}", old, new)
            raise GitError("Could not publish: the content repository rejected the change. Try again.")
        self._checkout_published()
        return new

    # --- owner changes on main ---------------------------------------------

    def change_main(self, message: str, author: Author, change: Callable[[Path], None]) -> str | None:
        """Apply ``change`` to a fresh checkout of main, then commit and publish it.

        ``change`` receives the checkout's root. If it raises, nothing is committed.
        """
        with self._lock:
            self._require_ready()
            self._fetch()
            self._fast_forward_main()
            with self._temporary_worktree() as tree:
                change(tree)
                return self._commit_to_main(tree, message, author)

    def remove_expired_archive(self, retention_days: int) -> list[str]:
        """Remove archived apps and notebooks older than the retention period from main.

        They stay in the repository's history. Returns the removed paths.
        """
        with self._lock:
            self._require_ready()
            if not expired_archive_entries(self.published, retention_days):
                return []
            removed: list[str] = []

            def change(tree: Path) -> None:
                removed.extend(remove_expired_archive(tree, retention_days))

            listing = "\n".join(
                f"- {entry.relative_to(self.published).as_posix()}"
                for entry in expired_archive_entries(self.published, retention_days)
            )
            self.change_main(
                f"Remove archived items older than {retention_days} days\n\n{listing}",
                Author(BOT_NAME, BOT_EMAIL),
                change,
            )
            return removed

    # --- editor workspaces ---------------------------------------------------

    @staticmethod
    def branch_name(app: str, user: str) -> str:
        return f"edit/{app}/{user}"

    def _check_names(self, app: str, user: str) -> None:
        if not SLUG_PATTERN.match(app) or not USER_PATTERN.match(user):
            raise GitError("Invalid app or user name")

    def workspace(self, app: str, user: str) -> Path:
        """The editor's worktree for an app, created on first use. Returns the app folder inside it."""
        self._check_names(app, user)
        branch = self.branch_name(app, user)
        path = self.work_root / user / app
        with self._lock:
            self._require_ready()
            if not (path / ".git").exists():
                shutil.rmtree(path, ignore_errors=True)
                path.parent.mkdir(parents=True, exist_ok=True)
                if self._ref_exists(f"refs/heads/{branch}"):
                    self._git("worktree", "add", "--quiet", str(path), branch)
                elif self._ref_exists(f"refs/remotes/origin/{branch}"):
                    # Restore work that was pushed before this server's storage was lost.
                    self._git("worktree", "add", "--quiet", "-b", branch, str(path), f"refs/remotes/origin/{branch}")
                else:
                    self._git("worktree", "add", "--quiet", "-b", branch, str(path), MAIN)
        return path / app

    def _worktree(self, app: str, user: str) -> Path:
        self._check_names(app, user)
        path = self.work_root / user / app
        if not (path / ".git").exists():
            raise GitError("No workspace for this app yet")
        return path

    def has_workspace(self, app: str, user: str) -> bool:
        self._check_names(app, user)
        return (self.work_root / user / app / ".git").exists()

    def pending_review(self, app: str, user: str) -> Review | None:
        """The user's submission for this app that is waiting for an owner, if any."""
        with self._lock:
            self._check_names(app, user)
            ref = f"{REVIEW_REFS}/{app}/{user}"
            if not self._ref_exists(ref):
                return None
            commit = self._out("rev-parse", ref)
            return Review(app=app, user=user, commit=commit, files=self.changed_files(app, commit))

    def status(self, app: str, user: str) -> WorkspaceStatus:
        with self._lock:
            tree = self._worktree(app, user)
            porcelain = self._git("status", "--porcelain", "-z", "--untracked-files=all", "--", f"{app}/", cwd=tree).stdout
            # Entries are "XY path", NUL-separated; renames are followed by their original path, which is skipped.
            entries = porcelain.split("\0")
            changed, index = [], 0
            while index < len(entries):
                entry = entries[index]
                if entry:
                    changed.append(entry[3:])
                    if entry[0] in "RC":
                        index += 1
                index += 1
            changed = tuple(changed)
            # Compare content rather than commits: after publishing, main has a merge
            # commit the branch lacks, but nothing in it is new to the editor.
            branch = self.branch_name(app, user)
            base = self._out("merge-base", MAIN, branch)
            ahead = self._out("diff", "--name-only", base, branch, "--", f"{app}/").splitlines()
            behind = self._out("diff", "--name-only", base, MAIN, "--", f"{app}/").splitlines()
            return WorkspaceStatus(changed=changed, ahead=len(ahead), behind=len(behind))

    def commit(self, app: str, user: str, message: str, author: Author) -> str | None:
        """Commit the editor's changes to the app folder and push their branch.

        app.toml is never included: members and visibility are changed by owners
        through the settings page. Returns the commit, or None if nothing changed.
        """
        message = message.strip() or "Update notebooks"
        with self._lock:
            tree = self._worktree(app, user)
            self._git("add", "--all", "--", f"{app}/", f":(exclude){app}/{APP_FILE}", cwd=tree)
            if self._git("diff", "--cached", "--quiet", cwd=tree, check=False).returncode == 0:
                return None
            self._git("commit", "--quiet", "-m", message, cwd=tree, author=author)
            self._push(self.branch_name(app, user))
            return self._out("rev-parse", "HEAD", cwd=tree)

    def discard(self, app: str, user: str) -> None:
        """Throw away uncommitted changes in the editor's app folder."""
        with self._lock:
            tree = self._worktree(app, user)
            self._git("checkout", "--quiet", "HEAD", "--", f"{app}/", cwd=tree, check=False)
            self._git("clean", "--quiet", "-fd", "--", f"{app}/", cwd=tree)

    def update_from_main(self, app: str, user: str, author: Author, prefer: str | None = None) -> None:
        """Merge the published version into the editor's branch.

        If the same lines changed on both sides, raises MergeConflict and leaves the
        branch unchanged, unless ``prefer`` is "mine" or "published": then that side
        wins for the conflicting lines and all other changes from both sides are kept.
        """
        strategy = {None: [], "mine": ["-X", "ours"], "published": ["-X", "theirs"]}
        if prefer not in strategy:
            raise ValueError(f"Unknown preference {prefer!r}")
        with self._lock:
            tree = self._worktree(app, user)
            if self.status(app, user).dirty:
                raise GitError("Commit or discard your changes before getting the latest version")
            self._fetch()
            self._fast_forward_main()
            result = self._git("merge", "--no-edit", "--quiet", *strategy[prefer], MAIN,
                               cwd=tree, author=author, check=False)
            if result.returncode != 0:
                files = self._out("diff", "--name-only", "--diff-filter=U", cwd=tree).splitlines()
                self._git("merge", "--abort", cwd=tree, check=False)
                raise MergeConflict(files or ["unknown files"])
            self._push(self.branch_name(app, user))

    # --- publishing and reviews ---------------------------------------------

    def changed_files(self, app: str, commit: str) -> tuple[str, ...]:
        """Files a commit changes compared to what is published."""
        base = self._out("merge-base", MAIN, commit)
        return tuple(self._out("diff", "--name-only", base, commit).splitlines())

    def _check_scope(self, app: str, commit: str, allow_app_file: bool) -> None:
        for path in self.changed_files(app, commit):
            if not path.startswith(f"{app}/"):
                raise GitError(f"The changes touch files outside this app ({path}) and cannot be published")
            if path == f"{app}/{APP_FILE}" and not allow_app_file:
                raise GitError(f"The changes modify {APP_FILE}, which only owners can change through settings")

    def publish_commit(self, app: str, commit: str, message: str, author: Author,
                       allow_app_file: bool = False) -> str:
        """Publish a commit's changes to main as a single new commit.

        Squashing keeps main's history to messages owners have confirmed; the
        commits made along the way stay on the editor's branch. Raises
        MergeConflict if the changes no longer apply cleanly.
        """
        with self._lock:
            self._fetch()
            self._fast_forward_main()
            self._check_scope(app, commit, allow_app_file)
            with self._temporary_worktree() as tree:
                result = self._git("merge", "--squash", "--quiet", commit, cwd=tree, check=False)
                if result.returncode != 0:
                    files = self._out("diff", "--name-only", "--diff-filter=U", cwd=tree).splitlines()
                    raise MergeConflict(files or ["unknown files"])
                if self._git("diff", "--cached", "--quiet", cwd=tree, check=False).returncode == 0:
                    raise GitError("These changes are already published")
                self._git("commit", "--quiet", "-m", message, cwd=tree, author=author)
                return self._publish_head(tree)

    def _reset_to_main(self, app: str, user: str) -> None:
        """Start the editor's branch again from main once everything on it is published."""
        tree = self._worktree(app, user)
        self._git("reset", "--quiet", "--hard", MAIN, cwd=tree)
        self._push(self.branch_name(app, user), force=True)

    def publish_workspace(self, app: str, user: str, message: str, author: Author) -> str | None:
        """Owner shortcut: publish everything in the owner's workspace without review."""
        with self._lock:
            self.commit(app, user, message, author)
            if self.status(app, user).ahead == 0:
                return None
            branch_head = self._out("rev-parse", self.branch_name(app, user))
            published = self.publish_commit(app, branch_head, message, author)
            self._reset_to_main(app, user)
            return published

    def submit_review(self, app: str, user: str) -> Review:
        """Ask owners to publish the editor's committed changes, as they are now."""
        with self._lock:
            self._worktree(app, user)
            if self.status(app, user).ahead == 0:
                raise GitError("There are no committed changes to submit")
            commit = self._out("rev-parse", self.branch_name(app, user))
            self._git("update-ref", f"{REVIEW_REFS}/{app}/{user}", commit)
            return Review(app=app, user=user, commit=commit, files=self.changed_files(app, commit))

    def reviews(self, app: str) -> list[Review]:
        with self._lock:
            refs = self._out("for-each-ref", "--format=%(refname) %(objectname)", f"{REVIEW_REFS}/{app}/")
            result = []
            for line in refs.splitlines():
                ref, commit = line.split()
                user = ref.rsplit("/", 1)[1]
                result.append(Review(app=app, user=user, commit=commit, files=self.changed_files(app, commit)))
            return result

    def review_diff(self, review: Review) -> str:
        base = self._out("merge-base", MAIN, review.commit)
        return self._out("diff", base, review.commit)

    def review_messages(self, review: Review) -> list[str]:
        """The editor's commit messages for the submitted changes, oldest first."""
        base = self._out("merge-base", MAIN, review.commit)
        return self._out("log", "--reverse", "--no-merges", "--format=%s", f"{base}..{review.commit}").splitlines()

    def approve(self, review: Review, owner: Author, message: str) -> str:
        """Publish a review as one commit credited to the editor, with the owner's message."""
        with self._lock:
            name, email = self._out("log", "-1", "--format=%an%x00%ae", review.commit).split("\0")
            full_message = f"{message}\n\nApproved-by: {owner.name} <{owner.email}>"
            new = self.publish_commit(review.app, review.commit, full_message, Author(name, email))
            self._git("update-ref", "-d", f"{REVIEW_REFS}/{review.app}/{review.user}")
            # Tidy the editor's branch if they have not continued working on it.
            branch = self.branch_name(review.app, review.user)
            if (self._out("rev-parse", branch) == review.commit
                    and not self.status(review.app, review.user).dirty):
                self._reset_to_main(review.app, review.user)
            return new

    def reject(self, review: Review) -> None:
        with self._lock:
            self._git("update-ref", "-d", f"{REVIEW_REFS}/{review.app}/{review.user}")


def author_for(user: User) -> Author:
    """Commit author for a signed-in user."""
    return Author(user.username, user.email or f"{user.username}@users.noreply.github.com")


def user_key(user: User) -> str:
    """Folder and branch name for a user. GitHub logins are case-insensitive."""
    return user.username.lower()


store = ContentStore(
    settings.data_dir,
    remote=settings.content_repo,
    token=settings.github_token,
    seed_dir=SAMPLE_CONTENT_DIR,
)
