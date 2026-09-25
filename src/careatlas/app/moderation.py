"""Checks on commit messages written in CareAtlas.

Messages must describe the change: long enough to be meaningful and not a
placeholder such as "update". Every commit is also authored by the signed-in
GitHub account, and only owner-confirmed messages reach the published history
(see ``ContentStore.publish_commit``).
"""

import re

MIN_MESSAGE_LENGTH = 10
MAX_MESSAGE_LENGTH = 200
PLACEHOLDER_MESSAGES = {
    "update", "updates", "updated", "change", "changes", "fix", "fixes", "test", "testing",
    "wip", "asdf", "commit", "save", "saved", "edit", "edits", "misc", "stuff", "todo",
    "update notebooks",
}


class TextError(ValueError):
    """A message that cannot be accepted. The text explains what to change."""


def validate_commit_message(message: str) -> str:
    """Return the cleaned message, or raise TextError explaining what to change."""
    cleaned = " ".join(message.split())
    if len(cleaned) < MIN_MESSAGE_LENGTH:
        raise TextError(f"Describe your changes in at least {MIN_MESSAGE_LENGTH} characters")
    if len(cleaned) > MAX_MESSAGE_LENGTH:
        raise TextError(f"Keep the description under {MAX_MESSAGE_LENGTH} characters")
    if cleaned.casefold().strip(" .!") in PLACEHOLDER_MESSAGES or len(re.findall(r"\w+", cleaned)) < 2:
        raise TextError("Say what changed, for example 'Add 2023 survey data to the map'")
    return cleaned
