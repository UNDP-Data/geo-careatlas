"""ASGI entry point: a FastAPI app with the NiceGUI frontend mounted on it."""

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from nicegui import app as nicegui_app
from nicegui import ui

from careatlas.app import auth, pages  # noqa: F401  pages registers routes on import
from careatlas.app.config import settings
from careatlas.app.content import GitError, store
from careatlas.app.editor import EDIT_PREFIX, edit_proxy, editors
from careatlas.app.runner import REVIEW_PREFIX, RUN_PREFIX, create_review_runner, create_runner

logging.basicConfig(level=logging.INFO)
logging.getLogger("nicegui").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
# UNDP's favicon, from https://www.undp.org/themes/custom/undpglobal/favicon.ico
FAVICON = STATIC_DIR / "undp" / "favicon.ico"
# How often to pick up changes pushed to the content repository from elsewhere.
REFRESH_SECONDS = 300
ARCHIVE_CLEANUP_SECONDS = 24 * 3600

app = FastAPI(title="UNDP CareAtlas")


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def prepare_content() -> None:
    try:
        await asyncio.to_thread(store.ensure)
        logger.info("Content ready in %s", settings.data_dir)
    except (GitError, OSError) as exc:
        logger.error("Content repository unavailable, no apps will be shown: %s", exc)
        return

    async def refresh_periodically() -> None:
        while True:
            await asyncio.sleep(REFRESH_SECONDS)
            try:
                await asyncio.to_thread(store.refresh)
            except (GitError, OSError) as exc:
                logger.warning("Could not refresh content: %s", exc)

    async def clean_archive_daily() -> None:
        while True:
            try:
                removed = await asyncio.to_thread(store.remove_expired_archive, settings.archive_retention_days)
                if removed:
                    logger.info("Removed expired archive entries: %s", ", ".join(removed))
            except (GitError, OSError) as exc:
                logger.warning("Could not clean up the archive: %s", exc)
            await asyncio.sleep(ARCHIVE_CLEANUP_SECONDS)

    asyncio.create_task(refresh_periodically())
    asyncio.create_task(editors.reap())
    if settings.archive_retention_days > 0:
        asyncio.create_task(clean_archive_daily())


app.mount(RUN_PREFIX, create_runner())
app.mount(REVIEW_PREFIX, create_review_runner())
app.mount(EDIT_PREFIX, edit_proxy)
nicegui_app.add_static_files("/static", STATIC_DIR)
nicegui_app.on_startup(prepare_content)
nicegui_app.on_shutdown(editors.stop_all)
nicegui_app.on_shutdown(auth.close)

ui.run_with(
    app,
    title="UNDP CareAtlas",
    favicon=FAVICON if FAVICON.is_file() else None,
    storage_secret=settings.storage_secret,
    show_welcome_message=False,
)
