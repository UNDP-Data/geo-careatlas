from careatlas.app import editor


def test_notebooks_do_not_inherit_server_secrets(monkeypatch):
    for name in editor.SECRET_ENV:
        monkeypatch.setenv(name, "secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("PYTHONPATH", "/server/src")
    env = editor.notebook_env()
    assert "secret" not in env.values()
    assert env["PYTHONPATH"] == "/server/src"


def test_user_settings_bind_run_all_and_keep_other_settings(tmp_path):
    import tomllib

    settings_file = tmp_path / ".marimo.toml"
    settings_file.write_text('[display]\ntheme = "dark"\n')
    editor.prepare_user_settings(tmp_path)
    editor.prepare_user_settings(tmp_path)
    saved = tomllib.loads(settings_file.read_text())
    assert saved["display"]["theme"] == "dark"
    assert saved["keymap"]["overrides"]["global.runAll"] == editor.RUN_ALL_HOTKEY
    assert saved["package_management"]["manager"] == "uv"


def test_notebooks_install_packages_into_the_environment_not_the_project(monkeypatch):
    monkeypatch.setenv("UV", "/uvbin/uv")
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "/server/.venv")
    monkeypatch.setenv("VIRTUAL_ENV", "/server/.venv")
    env = editor.notebook_env()
    assert "UV" not in env and "UV_PROJECT_ENVIRONMENT" not in env
    assert env["VIRTUAL_ENV"] == "/server/.venv"
