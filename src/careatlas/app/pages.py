"""Site pages. Importing this module registers the routes with NiceGUI."""

import asyncio
import dataclasses
import logging
from collections.abc import Callable
from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import ui

from careatlas.app.apps import App, AppConfigError, Notebook, Role, Visibility, load_app, visible_apps
from careatlas.app.auth import User, get_user, sign_in_url
from careatlas.app.config import settings
from careatlas.app.content import GitError, author_for, store
from careatlas.app.editing import editor_url, reviews_section
from careatlas.app.layout import confirm, frame, notice, page_title
from careatlas.app.manage import (
    archive_app,
    archive_notebook,
    create_app,
    create_notebook,
    normalize_members,
    save_app,
    slugify,
)
from careatlas.app.runner import notebook_url

logger = logging.getLogger(__name__)

ROLE_LABELS = {Role.OWNER: "Owner", Role.EDITOR: "Editor", Role.VIEWER: "Viewer"}
VISIBILITY_OPTIONS = {
    Visibility.RESTRICTED.value: "Restricted: only listed members can view",
    Visibility.PUBLIC.value: "Public: anyone can view, even without signing in",
}
NOT_FOUND = "This app does not exist or you do not have access to it."


def _load(slug: str) -> App | None:
    try:
        return load_app(settings.content_dir, slug)
    except AppConfigError as exc:
        logger.error("Invalid app %s: %s", slug, exc)
        return None


async def _owner_check(request: Request, slug: str) -> tuple[App, User] | None:
    """Re-check ownership when an action runs, since the page may have been open for a while."""
    user = await get_user(request)
    app = _load(slug)
    if app is None or user is None or app.role_for(user) is not Role.OWNER:
        ui.notify("Only owners of this app can do that.", type="negative")
        return None
    return app, user


def _owned_app(tree: Path, slug: str, user: User) -> App:
    """The app as it is on main right now, if the user still owns it there."""
    app = load_app(tree, slug)
    if app is None or app.role_for(user) is not Role.OWNER:
        raise AppConfigError("Only owners of this app can do that")
    return app


async def _commit_to_main(message: str, user: User, change: Callable[[Path], None]) -> bool:
    """Apply an owner's change to main, commit it as them and publish it. Reports errors to the user."""
    try:
        await asyncio.to_thread(store.change_main, message, author_for(user), change)
    except (AppConfigError, GitError) as exc:
        ui.notify(str(exc), type="negative")
        return False
    logger.info("%s: %s", user.username, message)
    return True


def _archive_note(plural: bool = False) -> str:
    """Sentence telling owners how long archived items are kept."""
    subject, pronoun = ("They are", "them") if plural else ("It is", "it")
    days = settings.archive_retention_days
    if days > 0:
        return f"{subject} kept in the archive for {days} days, during which an administrator can restore {pronoun}."
    return f"{subject} kept in the archive, from which an administrator can restore {pronoun}."


def _primary_button(label: str, on_click, icon: str | None = None) -> ui.button:
    return ui.button(label, icon=icon, on_click=on_click) \
        .props("unelevated no-wrap color=secondary").classes("undp-btn undp-btn--small")


def _secondary_button(label: str, on_click, icon: str | None = None) -> ui.button:
    return ui.button(label, icon=icon, on_click=on_click) \
        .props("outline no-wrap color=primary").classes("undp-btn undp-btn--small")


def _tags(app: App, user: User | None) -> None:
    with ui.row().classes("gap-2"):
        if app.visibility is Visibility.RESTRICTED:
            ui.label("Restricted").classes("undp-tag")
        role = app.member_role(user)
        if role is not None:
            ui.label(ROLE_LABELS[role]).classes("undp-tag undp-tag--accent")


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

        with ui.row().classes("undp-page-heading"):
            page_title("Apps")
            if user:
                _primary_button("New app", lambda: ui.navigate.to("/new"), icon="add")

        apps = visible_apps(settings.content_dir, user)
        if not apps:
            notice("No apps available." if user else "No public apps yet. Sign in to see apps shared with you.")
            return

        with ui.element("div").classes("undp-grid"):
            for app, _ in apps:
                with ui.link(target=f"/apps/{app.slug}").classes("undp-app-card"):
                    ui.label(app.title).classes("undp-app-card__title")
                    ui.label(app.description or "No description.").classes("undp-app-card__text")
                    _tags(app, user)


def _visibility_radio(value: Visibility) -> ui.radio:
    return ui.radio(VISIBILITY_OPTIONS, value=value.value).classes("undp-radio")


@ui.page("/new")
async def new_app_page(request: Request):
    user = await get_user(request)
    if user is None:
        if settings.auth_enabled:
            return RedirectResponse(sign_in_url(request), status_code=303)
        async with frame(request, "New app", user=None):
            notice("Sign-in is not configured, so apps cannot be created.")
        return

    async with frame(request, "New app", user=user):
        with ui.column().classes("undp-form"):
            title = ui.input("Title").props("outlined").classes("w-full")
            slug = ui.input("Address", prefix="/apps/").props("outlined").classes("w-full") \
                .tooltip("Lowercase letters, digits, '-' and '_'. Cannot be changed later.")
            # Keep the address in sync with the title until the user edits it themselves.
            last_title = {"value": ""}

            def on_title(event) -> None:
                if slug.value in ("", slugify(last_title["value"])):
                    slug.value = slugify(event.value or "")
                last_title["value"] = event.value or ""

            title.on_value_change(on_title)
            description = ui.textarea("Description").props("outlined autogrow").classes("w-full")
            ui.label("Who can view this app?").classes("undp-field-label")
            visibility = _visibility_radio(Visibility.RESTRICTED)
            ui.label("You will be the owner. You can add editors and viewers afterwards.") \
                .classes("text-grey-7")

            async def submit() -> None:
                creator = await get_user(request)
                if creator is None:
                    ui.notify("Your session has expired. Sign in again.", type="negative")
                    return
                new_slug = slug.value.strip()

                def change(tree: Path) -> None:
                    create_app(tree, new_slug, title.value, description.value, Visibility(visibility.value), creator)

                create_button.props("loading")
                try:
                    if await _commit_to_main(f"Create app {new_slug}", creator, change):
                        ui.navigate.to(f"/apps/{new_slug}")
                finally:
                    create_button.props(remove="loading")

            create_button = _primary_button("Create app", submit)


async def _add_notebook(request: Request, slug: str) -> None:
    with ui.dialog() as dialog, ui.card().classes("undp-dialog"):
        ui.label("New notebook").classes("undp-dialog__title")
        title = ui.input("Title").props("outlined dense").classes("w-full")
        name = ui.input("File name", suffix=".py").props("outlined dense").classes("w-full")
        title.on_value_change(lambda e: name.set_value(slugify(e.value or "")))
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat")
            _primary_button("Create", lambda: dialog.submit(True))
    created = await dialog
    dialog.delete()
    if not created:
        return

    checked = await _owner_check(request, slug)
    if checked is None:
        return
    _, user = checked
    notebook_name = name.value.strip()

    def change(tree: Path) -> None:
        create_notebook(_owned_app(tree, slug, user), notebook_name, title=title.value.strip() or None)

    if await _commit_to_main(f"Add notebook {slug}/{notebook_name}", user, change):
        ui.navigate.reload()


async def _archive_notebook(request: Request, slug: str, notebook_name: str) -> None:
    if not await confirm(
        "Archive notebook?",
        f"'{notebook_name}' will be removed from the app. {_archive_note()}",
        "Archive",
    ):
        return
    checked = await _owner_check(request, slug)
    if checked is None:
        return
    _, user = checked

    def change(tree: Path) -> None:
        app = _owned_app(tree, slug, user)
        notebook = next((n for n in app.notebooks() if n.name == notebook_name), None)
        if notebook is None:
            raise AppConfigError("That notebook no longer exists")
        archive_notebook(tree, app, notebook)

    if await _commit_to_main(f"Archive notebook {slug}/{notebook_name}", user, change):
        ui.navigate.reload()


def _notebook_card(request: Request, app: App, notebook: Notebook, role: Role) -> None:
    with ui.card().classes("undp-card undp-notebook"):
        with ui.row().classes("w-full justify-between items-start no-wrap"):
            ui.label(notebook.title).classes("undp-app-card__title")
            if role is Role.OWNER:
                ui.button(icon="archive", on_click=lambda: _archive_notebook(request, app.slug, notebook.name)) \
                    .props("flat round dense color=grey-8").tooltip("Archive notebook")
        ui.label(notebook.description or "No description.").classes("undp-app-card__text")
        with ui.row().classes("gap-6"):
            ui.link("Open", notebook_url(app.slug, notebook.name)).classes("undp-cta-link")
            if role >= Role.EDITOR:
                ui.link("Edit", editor_url(app.slug, notebook.name)).classes("undp-cta-link")


@ui.page("/apps/{slug}")
async def app_page(request: Request, slug: str):
    user = await get_user(request)
    app = _load(slug)
    role = app.role_for(user) if app else None
    if app is not None and role is None and user is None and settings.auth_enabled:
        return RedirectResponse(sign_in_url(request), status_code=303)

    if app is None or role is None:
        # Unknown and forbidden apps look the same, so restricted apps are not disclosed.
        async with frame(request, "App not found", user=user):
            notice(NOT_FOUND)
        return

    is_owner = role is Role.OWNER
    async with frame(request, app.title, user=user):
        if app.description:
            ui.label(app.description).classes("undp-lead")
        _tags(app, user)
        if role >= Role.EDITOR:
            with ui.row().classes("gap-2"):
                _secondary_button("Open editor", lambda: ui.navigate.to(editor_url(app.slug)), icon="edit")
                if is_owner:
                    _secondary_button("Settings", lambda: ui.navigate.to(f"/apps/{app.slug}/settings"),
                                      icon="settings")

        with ui.row().classes("undp-page-heading"):
            ui.label("Notebooks").classes("undp-section-title")
            if is_owner:
                _primary_button("New notebook", lambda: _add_notebook(request, app.slug), icon="add")
        notebooks = app.notebooks()
        if not notebooks:
            notice("This app has no notebooks yet.")
        with ui.element("div").classes("undp-grid"):
            for notebook in notebooks:
                _notebook_card(request, app, notebook, role)

        if is_owner:
            await reviews_section(request, app)

        ui.label("Members").classes("undp-section-title")
        with ui.element("div").classes("undp-members"):
            for label, members in (("Owners", app.owners), ("Editors", app.editors), ("Viewers", app.viewers)):
                shown = ", ".join(members) if members else "None"
                if label == "Viewers" and app.visibility is Visibility.PUBLIC:
                    shown = "Everyone (public app)"
                ui.label(label).classes("undp-members__role")
                ui.label(shown)


class MembersEditor:
    """Editable list of members for one role, rendered as removable chips."""

    def __init__(self, label: str, hint: str, members: tuple[str, ...]) -> None:
        self.members = list(members)
        with ui.column().classes("undp-members-editor"):
            ui.label(label).classes("undp-members__role")
            ui.label(hint).classes("text-grey-7 text-sm")
            self.chips = ui.row().classes("gap-2 items-center")
            with ui.row().classes("items-center gap-2 no-wrap w-full"):
                self.input = ui.input(placeholder="GitHub username or @org/team") \
                    .props("outlined dense").classes("flex-grow")
                self.input.on("keydown.enter", self.add)
                ui.button("Add", on_click=self.add).props("flat color=primary")
        self.render()

    def render(self) -> None:
        self.chips.clear()
        with self.chips:
            if not self.members:
                ui.label("None").classes("text-grey-7")
            for member in self.members:
                ui.chip(member, removable=True, on_value_change=lambda _, m=member: self.remove(m)) \
                    .props("square outline color=primary")

    def add(self) -> None:
        try:
            added = normalize_members(self.members + [self.input.value])
        except AppConfigError as exc:
            ui.notify(str(exc), type="negative")
            return
        self.members = list(added)
        self.input.value = ""
        self.render()

    def remove(self, member: str) -> None:
        self.members = [m for m in self.members if m != member]
        self.render()


@ui.page("/apps/{slug}/settings")
async def app_settings_page(request: Request, slug: str):
    user = await get_user(request)
    app = _load(slug)
    role = app.role_for(user) if app else None
    if app is not None and role is None and user is None and settings.auth_enabled:
        return RedirectResponse(sign_in_url(request), status_code=303)

    if app is None or role is None:
        async with frame(request, "App not found", user=user):
            notice(NOT_FOUND)
        return

    if role is not Role.OWNER:
        async with frame(request, app.title, user=user):
            notice("Only owners can change this app's settings.")
        return

    async with frame(request, f"{app.title}: settings", user=user):
        ui.link("Back to app", f"/apps/{app.slug}").classes("undp-back-link")

        with ui.column().classes("undp-form"):
            ui.label("General").classes("undp-section-title")
            title = ui.input("Title", value=app.title).props("outlined").classes("w-full")
            description = ui.textarea("Description", value=app.description) \
                .props("outlined autogrow").classes("w-full")
            ui.label("Who can view this app?").classes("undp-field-label")
            visibility = _visibility_radio(app.visibility)

            ui.label("Members").classes("undp-section-title")
            owners = MembersEditor("Owners", "Manage settings, members and notebooks, and approve changes.", app.owners)
            editors = MembersEditor("Editors", "Edit their own copy of the notebooks and submit changes for approval.", app.editors)
            viewers = MembersEditor("Viewers", "View the app. Only needed for restricted apps.", app.viewers)

            async def save() -> None:
                checked = await _owner_check(request, slug)
                if checked is None:
                    return
                _, editor = checked
                saved: list[App] = []

                def change(tree: Path) -> None:
                    saved.append(save_app(dataclasses.replace(
                        _owned_app(tree, slug, editor),
                        title=title.value,
                        description=description.value,
                        visibility=Visibility(visibility.value),
                        owners=tuple(owners.members),
                        editors=tuple(editors.members),
                        viewers=tuple(viewers.members),
                    )))

                if not await _commit_to_main(f"Update settings of {slug}", editor, change):
                    return
                if saved and saved[0].role_for(editor) is not Role.OWNER:
                    ui.navigate.to(f"/apps/{slug}")
                    return
                ui.notify("Settings saved.", type="positive")

            _primary_button("Save changes", save)

            ui.label("Archive app").classes("undp-section-title")
            ui.label(
                f"Removes the app and all its notebooks from CareAtlas. {_archive_note(plural=True)}"
            ).classes("text-grey-8")

            async def archive() -> None:
                if not await confirm(
                    "Archive this app?",
                    f"'{app.title}' and its notebooks will no longer be available.",
                    "Archive app",
                    require=app.slug,
                ):
                    return
                checked = await _owner_check(request, slug)
                if checked is None:
                    return
                _, editor = checked

                def change(tree: Path) -> None:
                    archive_app(tree, _owned_app(tree, slug, editor))

                if await _commit_to_main(f"Archive app {slug}", editor, change):
                    ui.navigate.to("/")

            _secondary_button("Archive app", archive, icon="archive")
