"""Runtime settings read from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

# Sample apps shipped with the code. They seed the local content repository
# when no CONTENT_REPO is configured, so development works without GitHub access.
SAMPLE_CONTENT_DIR = Path(__file__).resolve().parent.parent / "notebooks"


def _url(name: str) -> str:
    return os.getenv(name, "").strip().rstrip("/")


@dataclass(frozen=True)
class Settings:
    # oauth2-proxy base URL reachable from the app's network, used for
    # server-side session checks, e.g. http://auth-proxy:4180/oauth2
    auth_internal_url: str
    # oauth2-proxy base URL as seen by the browser, used for sign-in/sign-out
    # redirects, e.g. https://auth.undpgeohub.org/oauth2
    auth_public_url: str
    # Public origin of this app, e.g. https://careatlas.undpgeohub.org.
    # When empty it is derived from the request (forwarded headers first).
    public_url: str
    storage_secret: str | None
    # Where the content repository and the editors' worktrees are kept. Holds
    # uncommitted work, so it must be on persistent storage.
    data_dir: Path
    # Git URL of the content repository, e.g.
    # https://github.com/UNDP-Data/geo-careatlas-notebooks.git. When empty, a
    # local repository seeded with the sample apps is used and nothing is pushed.
    content_repo: str
    # Token used by the server for git fetch and push. Never passed to notebooks.
    github_token: str | None
    # Minutes without a browser connection before an editor session shuts down.
    edit_idle_minutes: int

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_internal_url and self.auth_public_url)

    @property
    def content_dir(self) -> Path:
        """The published version of all apps (a worktree on the main branch)."""
        return self.data_dir / "published"


settings = Settings(
    auth_internal_url=_url("AUTH_INTERNAL_URL"),
    auth_public_url=_url("AUTH_PUBLIC_URL"),
    public_url=_url("PUBLIC_URL"),
    storage_secret=os.getenv("NICEGUI_STORAGE_SECRET") or None,
    data_dir=Path(os.getenv("DATA_DIR") or Path.home() / ".careatlas").resolve(),
    content_repo=os.getenv("CONTENT_REPO", "").strip(),
    github_token=os.getenv("GITHUB_PAT_TOKEN") or None,
    edit_idle_minutes=int(os.getenv("EDIT_IDLE_MINUTES", "60")),
)
