"""Owner operations on apps: create, edit settings and members, add and archive notebooks.

Nothing is deleted outright. Archived apps and notebooks are moved to
``<content>/_archive/``, which is never listed or served (its name is not a
valid app slug), and can be restored by moving them back. Entries older than
the retention period are removed by ``expired_archive_entries`` and
``remove_expired_archive``; they remain in the repository's history.

Callers are responsible for checking that the user is allowed to perform the
operation (see ``pages.py``); this module only validates the data.
"""

import dataclasses
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import marimo

from careatlas.app.apps import APP_FILE, SLUG_PATTERN, App, AppConfigError, Notebook, Visibility, load_app
from careatlas.app.auth import User

ARCHIVE_DIR = "_archive"
TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
# Archive entries end with the time they were archived: "<app>-<timestamp>" or "<notebook>-<timestamp>.py"
ARCHIVE_ENTRY_PATTERN = re.compile(r"-(\d{8}-\d{6})(?:\.py)?$")
NOTEBOOK_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

_GITHUB_NAME = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})"
MEMBER_PATTERN = re.compile(rf"^(?:{_GITHUB_NAME}|@{_GITHUB_NAME}(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?)$")

# Placeholders are filled with Python literals (repr), so any title is safe to embed.
NOTEBOOK_TEMPLATE = '''{docstring}

import marimo

__generated_with = "{version}"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md({heading})
    return


if __name__ == "__main__":
    app.run()
'''


def slugify(text: str) -> str:
    """Suggested slug for a title, e.g. "Care Economy 2025" -> "care_economy_2025"."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def normalize_members(members: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Strip, validate and de-duplicate member entries (case-insensitively, keeping the first spelling)."""
    result: list[str] = []
    seen: set[str] = set()
    for member in members:
        member = member.strip()
        if not member:
            continue
        if not MEMBER_PATTERN.match(member):
            raise AppConfigError(f"'{member}' is not a GitHub username or @org/team")
        if member.lower() not in seen:
            seen.add(member.lower())
            result.append(member)
    return tuple(result)


def _render(app: App) -> str:
    def string(value: str) -> str:
        # JSON string escapes are valid TOML basic-string escapes.
        return json.dumps(value, ensure_ascii=False)

    def array(values: tuple[str, ...]) -> str:
        return "[" + ", ".join(string(v) for v in values) + "]"

    return "\n".join([
        "# Managed by CareAtlas. Edit through the app settings page where possible.",
        f"title = {string(app.title)}",
        f"description = {string(app.description)}",
        f"visibility = {string(app.visibility.value)}",
        "",
        "[members]",
        f"owners = {array(app.owners)}",
        f"editors = {array(app.editors)}",
        f"viewers = {array(app.viewers)}",
        "",
    ])


def _write_atomic(path: Path, content: str) -> None:
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)


def save_app(app: App) -> App:
    """Validate and write the app's settings and members to its app.toml."""
    title = app.title.strip()
    if not title:
        raise AppConfigError("Title is required")
    app = dataclasses.replace(
        app,
        title=title,
        description=app.description.strip(),
        owners=normalize_members(app.owners),
        editors=normalize_members(app.editors),
        viewers=normalize_members(app.viewers),
    )
    if not app.owners:
        raise AppConfigError("An app needs at least one owner")
    _write_atomic(app.path / APP_FILE, _render(app))
    return app


def create_app(
    content_dir: Path,
    slug: str,
    title: str,
    description: str,
    visibility: Visibility,
    creator: User,
) -> App:
    """Create an app owned by ``creator`` with one starter notebook."""
    if not SLUG_PATTERN.match(slug):
        raise AppConfigError("Use lowercase letters, digits, '-' and '_' for the address, starting with a letter or digit")
    if not creator.username:
        raise AppConfigError("Creating an app requires a GitHub username")
    path = content_dir / slug
    if path.exists():
        raise AppConfigError(f"An app with the address '{slug}' already exists")

    path.mkdir(parents=True)
    try:
        app = save_app(App(
            slug=slug,
            path=path,
            title=title,
            description=description,
            visibility=visibility,
            owners=(creator.username,),
            editors=(),
            viewers=(),
        ))
        create_notebook(app, "main", title="Overview")
    except BaseException:
        shutil.rmtree(path, ignore_errors=True)
        raise
    return app


def create_notebook(app: App, name: str, title: str | None = None) -> Notebook:
    """Add a notebook from the starter template."""
    if not NOTEBOOK_PATTERN.match(name):
        raise AppConfigError("Use lowercase letters, digits and '_' for the notebook name, starting with a letter")
    path = app.path / f"{name}.py"
    if path.exists():
        raise AppConfigError(f"A notebook named '{name}' already exists")
    title = title or name.replace("_", " ").capitalize()
    content = NOTEBOOK_TEMPLATE.format(
        docstring=repr(f"{title} notebook of {app.title}."),
        version=marimo.__version__,
        heading=repr(f"# {title}"),
    )
    _write_atomic(path, content)
    return Notebook(name=name, path=path)


def archive_notebook(content_dir: Path, app: App, notebook: Notebook) -> Path:
    """Move a notebook to <content>/_archive/<app>/ and return its new location."""
    if app.path not in notebook.path.parents:
        raise AppConfigError("Notebook does not belong to this app")
    target = content_dir / ARCHIVE_DIR / app.slug / f"{notebook.name.replace('/', '__')}-{_timestamp()}.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(notebook.path, target)
    return target


def archive_app(content_dir: Path, app: App) -> Path:
    """Move a whole app to <content>/_archive/ and return its new location."""
    if load_app(content_dir, app.slug) is None:
        raise AppConfigError(f"App '{app.slug}' does not exist")
    target = content_dir / ARCHIVE_DIR / f"{app.slug}-{_timestamp()}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(app.path, target)
    return target


def archived_at(entry: Path) -> datetime | None:
    """When an archive entry was archived, from its name. None if the name has no timestamp."""
    match = ARCHIVE_ENTRY_PATTERN.search(entry.name)
    if not match:
        return None
    return datetime.strptime(match.group(1), TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)


def archived_app_slug(entry: Path) -> str | None:
    """The app an archived app folder came from, e.g. "_archive/care-20260101-000000" -> "care"."""
    match = ARCHIVE_ENTRY_PATTERN.search(entry.name)
    if not match or entry.parent.name != ARCHIVE_DIR or entry.suffix == ".py":
        return None
    slug = entry.name[:match.start()]
    return slug if SLUG_PATTERN.match(slug) else None


def expired_archive_entries(content_dir: Path, retention_days: int, now: datetime | None = None) -> list[Path]:
    """Archived apps and notebooks older than the retention period, oldest first."""
    archive = content_dir / ARCHIVE_DIR
    if retention_days <= 0 or not archive.is_dir():
        return []
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    candidates = list(archive.iterdir())
    # Archived notebooks sit one level down, in a folder named after their app.
    for folder in [c for c in candidates if c.is_dir() and archived_at(c) is None]:
        candidates.extend(folder.iterdir())
    expired = [(when, entry) for entry in candidates if (when := archived_at(entry)) and when < cutoff]
    return [entry for _, entry in sorted(expired)]


def remove_expired_archive(content_dir: Path, retention_days: int, now: datetime | None = None) -> list[str]:
    """Delete expired archive entries and return their paths relative to the content directory."""
    removed = []
    for entry in expired_archive_entries(content_dir, retention_days, now):
        removed.append(entry.relative_to(content_dir).as_posix())
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
            if not any(entry.parent.iterdir()):
                entry.parent.rmdir()
    return removed
