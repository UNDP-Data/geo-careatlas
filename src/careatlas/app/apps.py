"""Apps and per-app access control.

An app is a folder in the content directory containing an ``app.toml`` and one
or more marimo notebooks::

    content/
      global_poverty/
        app.toml
        global_poverty.py

``app.toml`` holds the title, description, visibility and members::

    title = "Global Poverty"
    description = "..."
    visibility = "public"        # or "restricted"

    [members]
    owners = ["octocat"]
    editors = ["@UNDP-Data/geohub"]
    viewers = []

Members are GitHub usernames or teams written as ``@org/team`` (``@org`` for a
whole organisation). They are matched case-insensitively against the user's
login and the groups oauth2-proxy reports (``org`` and ``org:team``).
"""

import ast
import logging
import re
import tomllib
from dataclasses import dataclass
from enum import Enum, IntEnum
from pathlib import Path

from careatlas.app.auth import User

logger = logging.getLogger(__name__)

APP_FILE = "app.toml"
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
# A markdown heading line such as "# Care survey" or "## Results", without trailing #s
HEADING_PATTERN = re.compile(r"^\s*#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)


class Role(IntEnum):
    """Roles ordered by privilege, so a higher role includes the lower ones."""

    VIEWER = 1
    EDITOR = 2
    OWNER = 3


class Visibility(str, Enum):
    PUBLIC = "public"
    RESTRICTED = "restricted"


class AppConfigError(ValueError):
    """Raised when an app.toml is missing or invalid."""


@dataclass(frozen=True)
class Notebook:
    # Path relative to the app folder without the .py suffix, e.g. "thematic_areas/economic_outlook"
    name: str
    path: Path

    def _parse(self) -> ast.Module | None:
        try:
            return ast.parse(self.path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            return None

    @property
    def title(self) -> str:
        """The notebook's first markdown heading, falling back to its file name.

        Read from the source without running it: the first ``mo.md("# ...")`` in the file.
        """
        tree = self._parse()
        headings = []
        for node in ast.walk(tree) if tree else ():
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "md"
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                match = HEADING_PATTERN.search(node.args[0].value)
                if match:
                    headings.append((node.lineno, match.group(1).strip()))
        if headings:
            return min(headings)[1]
        return Path(self.name).name.replace("_", " ").capitalize()

    @property
    def description(self) -> str | None:
        """The notebook's module docstring, if any."""
        tree = self._parse()
        doc = ast.get_docstring(tree) if tree else None
        return " ".join(doc.split()) if doc else None


@dataclass(frozen=True)
class App:
    slug: str
    path: Path
    title: str
    description: str
    visibility: Visibility
    owners: tuple[str, ...]
    editors: tuple[str, ...]
    viewers: tuple[str, ...]

    def member_role(self, user: User | None) -> Role | None:
        """Highest role the user is explicitly listed for, ignoring public visibility."""
        if user is None:
            return None
        for role, members in (
            (Role.OWNER, self.owners),
            (Role.EDITOR, self.editors),
            (Role.VIEWER, self.viewers),
        ):
            if _matches(user, members):
                return role
        return None

    def role_for(self, user: User | None) -> Role | None:
        """Effective role in this app, or None if the user cannot view it."""
        role = self.member_role(user)
        if role is None and self.visibility is Visibility.PUBLIC:
            return Role.VIEWER
        return role

    def notebooks(self) -> list[Notebook]:
        """Notebooks in the app, skipping private modules (leading underscore) as marimo does."""
        found = []
        for path in sorted(self.path.rglob("*.py")):
            relative = path.relative_to(self.path).with_suffix("")
            if any(part.startswith("_") for part in relative.parts):
                continue
            found.append(Notebook(name=relative.as_posix(), path=path))
        return found


def _matches(user: User, members: tuple[str, ...]) -> bool:
    login = user.username.lower()
    groups = {g.lower() for g in user.groups}
    for member in members:
        member = member.strip().lower()
        if member.startswith("@"):
            # "@org/team" corresponds to the oauth2-proxy group "org:team"
            if member[1:].replace("/", ":", 1) in groups:
                return True
        elif login and member == login:
            return True
    return False


def _members(raw: dict, key: str) -> tuple[str, ...]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(m, str) for m in value):
        raise AppConfigError(f"members.{key} must be a list of strings")
    return tuple(m.strip() for m in value if m.strip())


def load_app(content_dir: Path, slug: str) -> App | None:
    """Load one app by slug. Returns None if it does not exist.

    Raises AppConfigError if the app exists but its app.toml is invalid.
    """
    if not SLUG_PATTERN.match(slug):
        return None
    path = content_dir / slug
    config_file = path / APP_FILE
    if not config_file.is_file():
        return None

    try:
        raw = tomllib.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise AppConfigError(f"{config_file}: {exc}") from exc

    try:
        visibility = Visibility(raw.get("visibility", Visibility.RESTRICTED.value))
    except ValueError as exc:
        raise AppConfigError(f"{config_file}: visibility must be 'public' or 'restricted'") from exc

    members = raw.get("members", {})
    if not isinstance(members, dict):
        raise AppConfigError(f"{config_file}: [members] must be a table")

    return App(
        slug=slug,
        path=path,
        title=str(raw.get("title") or slug.replace("_", " ").title()),
        description=str(raw.get("description", "")),
        visibility=visibility,
        owners=_members(members, "owners"),
        editors=_members(members, "editors"),
        viewers=_members(members, "viewers"),
    )


def list_apps(content_dir: Path) -> list[App]:
    """All valid apps in the content directory, sorted by title. Invalid ones are logged and skipped."""
    apps = []
    if not content_dir.is_dir():
        logger.warning("Content directory %s does not exist", content_dir)
        return apps
    for child in sorted(content_dir.iterdir()):
        if not child.is_dir():
            continue
        try:
            app = load_app(content_dir, child.name)
        except AppConfigError as exc:
            logger.error("Skipping app %s: %s", child.name, exc)
            continue
        if app is not None:
            apps.append(app)
    return sorted(apps, key=lambda a: a.title.lower())


def visible_apps(content_dir: Path, user: User | None) -> list[tuple[App, Role]]:
    """Apps the user can view, with their role in each."""
    result = []
    for app in list_apps(content_dir):
        role = app.role_for(user)
        if role is not None:
            result.append((app, role))
    return result
