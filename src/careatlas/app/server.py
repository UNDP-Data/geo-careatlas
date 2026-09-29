"""ASGI entry point: a FastAPI app with the NiceGUI frontend mounted on it."""

import logging
from pathlib import Path

from fastapi import FastAPI
from nicegui import app as nicegui_app
from nicegui import ui

from careatlas.app import auth, pages  # noqa: F401  pages registers routes on import
from careatlas.app.config import settings

logging.basicConfig(level=logging.INFO)
logging.getLogger("nicegui").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="UNDP CareAtlas")


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


nicegui_app.add_static_files("/static", STATIC_DIR)
nicegui_app.on_shutdown(auth.close)

ui.run_with(
    app,
    title="UNDP CareAtlas",
    storage_secret=settings.storage_secret,
    show_welcome_message=False,
)
