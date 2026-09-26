"""Shared page chrome following the UNDP Design System (https://design.undp.org).

The header follows the "Country Site Header" component with its full-screen
mobile navigation, and the footer the "simple" variant of the "Footer"
component. The language switcher and search are left out, since CareAtlas does
not provide them.
"""

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import Request
from nicegui import ui

from careatlas.app.auth import User, get_user, sign_in_url, sign_out_url
from careatlas.app.config import settings

UNDP_BLUE = "#006eb5"
UNDP_RED = "#d12800"
STATIC_DIR = Path(__file__).parent / "static"
ASSETS = "/static/undp"
REPO_URL = "https://github.com/UNDP-Data/geo-careatlas"
GEOHUB_URL = "https://geohub.data.undp.org"


NAV_ITEMS = [
    ("Apps", "/"),
    ("Gender Equality", "https://www.undp.org/gender-equality"),
    ("GeoHub", GEOHUB_URL),
]

FOOTER_LINKS = [
    ("About UNDP", "https://www.undp.org/about-us"),
    ("GeoHub", GEOHUB_URL),
    ("Terms of use", "https://www.undp.org/copyright-terms-use"),
    ("Source code", REPO_URL),
]

SOCIAL_LINKS = [
    ("X", "https://x.com/UNDP", "twitter-x-white.svg"),
    ("LinkedIn", "https://www.linkedin.com/company/undp/", "linkedin-white.svg"),
    ("Facebook", "https://www.facebook.com/UNDP", "facebook-white.svg"),
    ("Instagram", "https://www.instagram.com/UNDP/", "instagram-white.svg"),
    ("YouTube", "https://www.youtube.com/UNDP/", "youtube-white.svg"),
]


def _is_external(url: str) -> bool:
    return url.startswith("http")


def _is_active(path: str, current: str) -> bool:
    if _is_external(path):
        return False
    if path == "/":
        # App pages live under /apps/ and belong to the "Apps" section.
        return current == "/" or current.startswith("/apps/")
    return current.startswith(path)


def _link(label: str, url: str) -> ui.link:
    return ui.link(label, url, new_tab=_is_external(url))


def _img(src: str, alt: str) -> ui.element:
    return ui.element("img").props(f'src="{src}" alt="{alt}"')


def _asset_url(name: str) -> str:
    """URL of a static file, versioned by its modification time.

    Checked on every render so an edited file gets a new URL even when the
    server has not restarted, and browsers never serve a stale cached copy.
    """
    version = int((STATIC_DIR / name).stat().st_mtime)
    return f"/static/{name}?v={version}"


def _theme() -> None:
    ui.colors(primary=UNDP_BLUE, secondary=UNDP_RED)
    ui.add_head_html(
        f'<link rel="stylesheet" href="{_asset_url("theme.css")}">'
        f'<script src="{_asset_url("nav.js")}"></script>'
    )


def _account(request: Request, user: User | None) -> None:
    if not settings.auth_enabled:
        return

    if user is None:
        url = sign_in_url(request)
        ui.button("Sign in", on_click=lambda: ui.navigate.to(url)) \
            .props("unelevated no-wrap color=secondary").classes("undp-btn undp-btn--small")
        return

    url = sign_out_url(request)
    with ui.button().props("flat no-caps").classes("undp-account") \
            .props(f'aria-label="Account: {user.display_name}"'):
        _avatar(user)
        ui.label(user.display_name).classes("undp-account__name gt-sm")
        with ui.menu().props('anchor="bottom right" self="top right"'):
            with ui.column().classes("px-4 py-3 gap-0"):
                ui.label(user.display_name).classes("font-semibold")
                ui.label(user.email).classes("text-xs text-grey-7")
            ui.separator()
            ui.menu_item("Sign out", on_click=lambda: ui.navigate.to(url))


def _initials(user: User) -> str:
    parts = [p for p in re.split(r"[\s._@-]+", user.display_name) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def _avatar(user: User) -> None:
    """The user's GitHub profile picture, over their initials in case it can't be loaded."""
    with ui.element("span").classes("undp-avatar").props('aria-hidden="true"'):
        ui.label(_initials(user)).classes("undp-avatar__initials")
        if user.username:
            ui.element("img").props(
                f'src="https://github.com/{quote(user.username)}.png?size=80" alt="" '
                'loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()"'
            )


def _hamburger() -> None:
    with ui.element("button").classes("undp-hamburger") \
            .props('type="button" aria-label="Open menu" aria-expanded="false" aria-controls="undp-mobile-nav"') \
            .on("click", js_handler="() => undpToggleNav()"):
        for position in ("top", "middle", "bottom"):
            ui.element("span").classes(f"undp-hamburger__line undp-hamburger__line--{position}")


def _mobile_nav(request: Request, user: User | None, current: str) -> None:
    with ui.element("div").classes("undp-mobile-nav").props('id="undp-mobile-nav"'):
        with ui.element("ul").classes("undp-mobile-nav__links"):
            for label, url in NAV_ITEMS:
                with ui.element("li"):
                    link = _link(label, url).classes("undp-cta-link")
                    if _is_active(url, current):
                        link.props('aria-current="page"')

        if settings.auth_enabled:
            with ui.element("div").classes("undp-mobile-nav__options"):
                if user is None:
                    ui.link("Sign in", sign_in_url(request))
                else:
                    with ui.row().classes("undp-mobile-nav__user items-center no-wrap gap-3"):
                        _avatar(user)
                        with ui.column().classes("gap-0"):
                            ui.label(user.display_name).classes("font-semibold text-black")
                            ui.label(user.email).classes("text-xs")
                    ui.link("Sign out", sign_out_url(request))


def _header(request: Request, user: User | None) -> None:
    current = request.url.path
    with ui.header().classes("undp-header"):
        with ui.element("div").classes("undp-header__inner"):
            with ui.link(target="/").classes("undp-header__logo"):
                _img(f"{ASSETS}/undp-logo-blue.svg", "UNDP logo")
            with ui.link(target="/").classes("undp-site-title"):
                ui.label("Gender Team").classes("undp-site-title__region")
                ui.label("CareAtlas").classes("undp-site-title__name")

            with ui.element("nav").classes("undp-menu gt-sm"):
                for label, url in NAV_ITEMS:
                    link = _link(label, url).classes("undp-menu__link")
                    if _is_active(url, current):
                        link.classes("undp-menu__link--active").props('aria-current="page"')

            with ui.element("div").classes("undp-header__actions"):
                with ui.element("div").classes("gt-sm"):
                    _account(request, user)
                _hamburger()

        _mobile_nav(request, user, current)


def _footer() -> None:
    with ui.footer(fixed=False).classes("undp-footer"):
        with ui.element("div").classes("undp-footer__inner"):
            with ui.element("div").classes("undp-footer__top"):
                with ui.element("div").classes("undp-footer__brand"):
                    with ui.link(target="https://www.undp.org", new_tab=True).classes("undp-footer__logo"):
                        _img(f"{ASSETS}/undp-logo-white.svg", "UNDP logo")
                    ui.html("United Nations<br>Development Programme").classes("undp-footer__name")
                with ui.element("div").classes("undp-footer__social"):
                    for name, url, icon in SOCIAL_LINKS:
                        with ui.link(target=url, new_tab=True).props(f'aria-label="{name}" title="{name}"'):
                            _img(f"{ASSETS}/{icon}", name)

            with ui.element("div").classes("undp-footer__bottom"):
                ui.label("© United Nations Development Programme").classes("undp-footer__copyright")
                with ui.element("nav").classes("undp-footer__links"):
                    for label, url in FOOTER_LINKS:
                        _link(label, url).classes("undp-footer__link")


def page_title(title: str) -> None:
    with ui.column().classes("gap-2"):
        ui.element("div").classes("undp-title__bar")
        ui.label(title).classes("undp-title")


_UNSET = object()


@asynccontextmanager
async def frame(
    request: Request,
    title: str | None = None,
    user: User | None = _UNSET,
    wide: bool = False,
) -> AsyncIterator[User | None]:
    """Render the shared chrome around a page and yield the current user.

    Pass ``user`` when the page has already looked it up, to avoid a second
    round trip to oauth2-proxy. ``wide`` uses the full window without a footer,
    for tools such as the notebook editor.
    """
    if user is _UNSET:
        user = await get_user(request)
    _theme()
    _header(request, user)
    with ui.column().classes("undp-editor-main" if wide else "undp-container undp-main"):
        if title:
            page_title(title)
        yield user
    if not wide:
        _footer()


def notice(text: str) -> None:
    with ui.card().classes("undp-card w-full"):
        ui.label(text).classes("text-grey-8")


async def confirm(title: str, text: str, action: str, require: str | None = None) -> bool:
    """Ask for confirmation in a dialog. With ``require``, the user must type that text to proceed."""
    with ui.dialog() as dialog, ui.card().classes("undp-dialog"):
        ui.label(title).classes("undp-dialog__title")
        ui.label(text)
        typed = None
        if require:
            typed = ui.input(f"Type {require} to confirm").props("outlined dense").classes("w-full")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat")
            button = ui.button(action, on_click=lambda: dialog.submit(True)) \
                .props("unelevated color=secondary").classes("undp-btn undp-btn--small")
            if typed is not None:
                button.bind_enabled_from(typed, "value", backward=lambda value: value == require)
    result = await dialog
    dialog.delete()
    return bool(result)
