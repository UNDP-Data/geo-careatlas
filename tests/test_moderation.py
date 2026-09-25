import pytest

from careatlas.app.moderation import TextError, validate_commit_message


@pytest.mark.parametrize("message", ["", "short", "Update notebooks", "update.", "asdfasdfasdfasdf", "x" * 201])
def test_weak_commit_messages_are_rejected(message):
    with pytest.raises(TextError):
        validate_commit_message(message)


def test_commit_message_is_cleaned():
    assert validate_commit_message("  Add   2023 survey\ndata  ") == "Add 2023 survey data"
