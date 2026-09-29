"""Site pages. Importing this module registers the routes with NiceGUI."""

from fastapi import Request
from nicegui import ui

from careatlas.app.auth import sign_in_url
from careatlas.app.config import settings
from careatlas.app.layout import frame, page_title


@ui.page("/")
async def home(request: Request) -> None:
    async with frame(request) as user:
        with ui.column().classes("undp-hero"):
            ui.label("CareAtlas").classes("undp-hero__title")
            ui.label(
                "Interactive notebooks and maps on care, gender and development, "
                "published by the UNDP Gender Team."
            ).classes("undp-hero__lead")
            if user:
                ui.label(f"Signed in as {user.display_name}").classes("undp-hero__meta")
            elif settings.auth_enabled:
                url = sign_in_url(request)
                ui.button("Sign in with GitHub", on_click=lambda: ui.navigate.to(url)) \
                    .props("unelevated no-wrap color=secondary").classes("undp-btn")

        page_title("Apps")
        with ui.card().classes("undp-card w-full"):
            ui.label("No apps published yet.").classes("text-grey-7")
