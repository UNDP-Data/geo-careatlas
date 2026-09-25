"""Editing notebooks: the editor page with its save/commit/publish toolbar, and owners' reviews.

What each action shares:

- Editing: marimo saves to the editor's worktree on the server. Only they see it.
- Commit changes: commits the app folder on their branch and pushes the branch.
  Visible on GitHub, not in CareAtlas.
- Submit for review (editors): asks owners to publish the committed changes.
- Publish (owners): commits and merges into main. Visible to all viewers.
"""

import asyncio
import logging
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import ui

from careatlas.app.apps import App, AppConfigError, Role, load_app
from careatlas.app.auth import User, get_user, sign_in_url
from careatlas.app.config import settings
from careatlas.app.content import GitError, MergeConflict, Review, author_for, store, user_key
from careatlas.app.editor import editors
from careatlas.app.layout import confirm, frame, notice
from careatlas.app.moderation import TextError, validate_commit_message

logger = logging.getLogger(__name__)

STATUS_SECONDS = 5.0


def editor_url(slug: str, notebook: str | None = None) -> str:
    return f"/apps/{slug}/edit" + (f"?notebook={quote(notebook)}" if notebook else "")


def _load(slug: str) -> App | None:
    try:
        return load_app(settings.content_dir, slug)
    except AppConfigError:
        return None


async def _current_role(request: Request, slug: str) -> tuple[User, Role] | None:
    """The user's role in the app right now; actions re-check it because pages stay open."""
    user = await get_user(request)
    app = _load(slug)
    role = app.role_for(user) if app and user else None
    if user is None or role is None or role < Role.EDITOR:
        ui.notify("You no longer have edit access to this app.", type="negative")
        return None
    return user, role


def _button(label: str, on_click, primary: bool = False, icon: str | None = None) -> ui.button:
    props = "unelevated no-wrap color=secondary" if primary else "outline no-wrap color=primary"
    return ui.button(label, icon=icon, on_click=on_click).props(props).classes("undp-btn undp-btn--small")


async def _ask_message(title: str, action: str, hint: str, value: str = "") -> str | None:
    """Ask for a description of the changes; stays open until it passes the message checks."""
    with ui.dialog() as dialog, ui.card().classes("undp-dialog"):
        ui.label(title).classes("undp-dialog__title")
        ui.label(hint).classes("text-grey-8 text-sm")
        message = ui.textarea("Describe your changes", value=value,
                              placeholder="e.g. Add 2023 survey data to the poverty map") \
            .props("outlined autogrow").classes("w-full")
        error = ui.label().classes("text-negative text-sm")

        def submit() -> None:
            try:
                dialog.submit(validate_commit_message(message.value))
            except TextError as exc:
                error.text = str(exc)

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat")
            _button(action, submit, primary=True)
    result = await dialog
    dialog.delete()
    return result


@ui.page("/apps/{slug}/edit")
async def edit_page(request: Request, slug: str, notebook: str | None = None):
    user = await get_user(request)
    app = _load(slug)
    role = app.role_for(user) if app else None
    if app is not None and user is None and settings.auth_enabled:
        return RedirectResponse(sign_in_url(request), status_code=303)
    if app is None or role is None or role < Role.EDITOR:
        async with frame(request, "App not found", user=user):
            notice("This app does not exist or you cannot edit it.")
        return

    try:
        session = await editors.open(user, slug)
    except (GitError, RuntimeError) as exc:
        logger.error("Could not open editor for %s on %s: %s", user.username, slug, exc)
        async with frame(request, app.title, user=user):
            notice(f"The editor could not be opened: {exc}")
        return

    key = user_key(user)
    is_owner = role is Role.OWNER
    notebook_file = notebook if notebook and any(n.name == notebook for n in app.notebooks()) else None

    async with frame(request, user=user, wide=True):
        with ui.row().classes("undp-editor-toolbar"):
            with ui.column().classes("gap-0"):
                ui.link(f"← {app.title}", f"/apps/{slug}").classes("undp-back-link")
                status = ui.label("Checking for changes…").classes("undp-editor-status")
            with ui.row().classes("gap-2 items-center"):
                discard_button = _button("Discard changes", lambda: discard(), icon="undo")
                latest_button = _button("Get latest", lambda: get_latest(), icon="sync")
                commit_button = _button("Commit changes", lambda: commit(), icon="save", primary=not is_owner)
                if is_owner:
                    share_button = _button("Publish", lambda: publish(), icon="publish", primary=True)
                else:
                    share_button = _button("Submit for review", lambda: submit(), icon="send", primary=True)

        ui.element("iframe").props(f'src="{session.url(notebook_file)}" title="Notebook editor"') \
            .classes("undp-editor-frame")

        async def refresh() -> None:
            try:
                state = await asyncio.to_thread(store.status, slug, key)
            except GitError as exc:
                status.text = str(exc)
                return
            parts = []
            if state.changed:
                count = len(state.changed)
                parts.append(f"{count} file{'s' if count != 1 else ''} changed, saved only on the server")
            if state.ahead:
                parts.append("committed changes not published yet")
            if state.behind:
                parts.append("a newer version has been published")
            status.text = "; ".join(parts).capitalize() if parts else "No changes. Everything is published."
            commit_button.set_enabled(state.dirty)
            discard_button.set_enabled(state.dirty)
            latest_button.set_enabled(bool(state.behind) and not state.dirty)
            share_button.set_enabled(state.dirty or bool(state.ahead) if is_owner else bool(state.ahead) and not state.dirty)

        toolbar_buttons = [discard_button, latest_button, commit_button, share_button]

        async def run(action, success: str) -> None:
            checked = await _current_role(request, slug)
            if checked is None:
                return
            # Commits and publishing push to GitHub and can take a few seconds.
            for button in toolbar_buttons:
                button.disable()
            status.text = "Working…"
            try:
                await asyncio.to_thread(action, checked[0])
            except MergeConflict as exc:
                ui.notify(f"{exc}. Use 'Get latest' first and choose which version to keep.",
                          type="warning", multi_line=True, timeout=0, close_button=True)
            except GitError as exc:
                ui.notify(str(exc), type="negative")
            else:
                ui.notify(success, type="positive")
            await refresh()

        async def commit() -> None:
            message = await _ask_message(
                "Commit changes", "Commit",
                "Saved to your branch on GitHub. Owners see this description when you submit for review.",
            )
            if message is not None:
                await run(lambda u: store.commit(slug, key, message, author_for(u)),
                          "Committed and pushed to your branch. Not published yet.")

        async def discard() -> None:
            if await confirm("Discard changes?",
                             "All changes since your last commit will be lost.", "Discard"):
                await run(lambda _: store.discard(slug, key), "Changes discarded.")

        async def get_latest() -> None:
            checked = await _current_role(request, slug)
            if checked is None:
                return
            author = author_for(checked[0])
            try:
                await asyncio.to_thread(store.update_from_main, slug, key, author)
            except MergeConflict as exc:
                prefer = await _choose_side(exc.files)
                if prefer is None:
                    await refresh()
                    return
                await run(lambda _: store.update_from_main(slug, key, author, prefer=prefer),
                          "Your copy now includes the latest published version.")
                return
            except GitError as exc:
                ui.notify(str(exc), type="negative")
            else:
                ui.notify("Your copy now includes the latest published version.", type="positive")
            await refresh()

        async def submit() -> None:
            await run(lambda _: store.submit_review(slug, key),
                      "Submitted. Owners can review and publish it from the app page.")

        async def publish() -> None:
            checked = await _current_role(request, slug)
            if checked is None or checked[1] is not Role.OWNER:
                ui.notify("Only owners can publish directly.", type="negative")
                return
            message = await _ask_message(
                "Publish changes", "Publish",
                "This description is recorded in the app's public history.",
            )
            if message is not None:
                await run(lambda u: store.publish_workspace(slug, key, message, author_for(u)),
                          "Published. Viewers now see this version.")

        await refresh()
        ui.timer(STATUS_SECONDS, refresh)


async def _choose_side(files: list[str]) -> str | None:
    """Ask how to resolve conflicting lines. Returns "mine", "published" or None to cancel."""
    names = ", ".join(f.split("/", 1)[-1] for f in files)
    with ui.dialog() as dialog, ui.card().classes("undp-dialog"):
        ui.label("Your changes overlap with the published version").classes("undp-dialog__title")
        ui.label(
            f"You and someone else changed the same lines in {names}. Choose which version to keep "
            "for those lines. All other changes, yours and theirs, are kept either way."
        )
        with ui.column().classes("w-full gap-2"):
            _button("Keep my version", lambda: dialog.submit("mine"), primary=True).classes("w-full")
            _button("Use the published version", lambda: dialog.submit("published")).classes("w-full")
            ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat").classes("w-full")
    result = await dialog
    dialog.delete()
    return result


async def reviews_section(request: Request, app: App) -> None:
    """Pending review requests for owners, with the changes and approve/reject actions."""
    try:
        reviews = await asyncio.to_thread(store.reviews, app.slug)
    except GitError as exc:
        logger.error("Could not list reviews for %s: %s", app.slug, exc)
        return

    ui.label("Changes awaiting review").classes("undp-section-title")
    if not reviews:
        notice("No changes are waiting for review.")
        return

    for review in reviews:
        with ui.card().classes("undp-card w-full"):
            with ui.row().classes("w-full justify-between items-center"):
                with ui.column().classes("gap-1"):
                    ui.label(f"From {review.user}").classes("undp-app-card__title")
                    ui.label(", ".join(f.split("/", 1)[1] for f in review.files) or "No file changes") \
                        .classes("text-grey-8")
                with ui.row().classes("gap-2"):
                    _button("View changes", lambda r=review: _show_diff(r))
                    _button("Reject", lambda r=review: _decide(request, r, approve=False))
                    _button("Approve and publish", lambda r=review: _decide(request, r, approve=True), primary=True)


async def _show_diff(review: Review) -> None:
    diff = await asyncio.to_thread(store.review_diff, review)
    with ui.dialog().props("maximized") as dialog, ui.card().classes("w-full h-full"):
        with ui.row().classes("w-full justify-between items-center"):
            ui.label(f"Changes from {review.user}").classes("undp-dialog__title")
            ui.button(icon="close", on_click=dialog.close).props("flat round")
        ui.code(diff or "No changes.", language="diff").classes("w-full undp-diff")
    dialog.open()


async def _decide(request: Request, review: Review, approve: bool) -> None:
    user = await get_user(request)
    app = _load(review.app)
    if user is None or app is None or app.role_for(user) is not Role.OWNER:
        ui.notify("Only owners can review changes.", type="negative")
        return
    if approve:
        messages = await asyncio.to_thread(store.review_messages, review)
        summary = "; ".join(dict.fromkeys(messages))[:200]
        message = await _ask_message(
            "Approve and publish",
            "Publish",
            f"The changes from {review.user} will be visible to everyone who can view this app. "
            "Confirm or rewrite the description; it is recorded in the app's public history.",
            value=summary,
        )
        if message is None:
            return
        try:
            await asyncio.to_thread(store.approve, review, author_for(user), message)
        except MergeConflict as exc:
            ui.notify(f"{exc}. Ask {review.user} to use 'Get latest', choose which version to keep, "
                      "and submit again.",
                      type="warning", multi_line=True, timeout=0, close_button=True)
            return
        except GitError as exc:
            ui.notify(str(exc), type="negative")
            return
        logger.info("%s approved changes from %s on %s", user.username, review.user, review.app)
    else:
        if not await confirm("Reject these changes?",
                             f"{review.user}'s changes stay on their branch but are removed from review.", "Reject"):
            return
        await asyncio.to_thread(store.reject, review)
        logger.info("%s rejected changes from %s on %s", user.username, review.user, review.app)
    ui.navigate.reload()
