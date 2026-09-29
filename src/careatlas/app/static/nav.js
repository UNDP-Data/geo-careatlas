// Full-screen mobile navigation. The open state lives on <body> so the
// hamburger, the panel and the page scroll lock all follow one class.
function undpToggleNav(open) {
    const isOpen = document.body.classList.toggle("undp-nav-open", open);
    document.querySelectorAll(".undp-hamburger").forEach((button) => {
        button.setAttribute("aria-expanded", String(isOpen));
        button.setAttribute("aria-label", isOpen ? "Close menu" : "Open menu");
    });
}

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") undpToggleNav(false);
});

document.addEventListener("click", (event) => {
    if (event.target.closest(".undp-mobile-nav a")) undpToggleNav(false);
});
