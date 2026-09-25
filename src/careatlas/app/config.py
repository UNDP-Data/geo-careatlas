"""Runtime settings read from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

# Sample apps shipped with the code, used until the separate content repository exists.
DEFAULT_CONTENT_DIR = Path(__file__).resolve().parent.parent / "notebooks"


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
    # Directory holding the apps: one folder per app with an app.toml and its notebooks.
    content_dir: Path

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_internal_url and self.auth_public_url)


settings = Settings(
    auth_internal_url=_url("AUTH_INTERNAL_URL"),
    auth_public_url=_url("AUTH_PUBLIC_URL"),
    public_url=_url("PUBLIC_URL"),
    storage_secret=os.getenv("NICEGUI_STORAGE_SECRET") or None,
    content_dir=Path(os.getenv("CONTENT_DIR") or DEFAULT_CONTENT_DIR).resolve(),
)
