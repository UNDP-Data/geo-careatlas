from careatlas.app import editor


def test_notebooks_do_not_inherit_server_secrets(monkeypatch):
    for name in editor.SECRET_ENV:
        monkeypatch.setenv(name, "secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("PYTHONPATH", "/server/src")
    env = editor._notebook_env()
    assert "secret" not in env.values()
    assert env["PYTHONPATH"] == "/server/src"
