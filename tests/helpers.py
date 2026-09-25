from pathlib import Path


def write_app(content: Path, slug: str, toml: str, notebooks: tuple[str, ...] = ("main.py",)) -> Path:
    folder = content / slug
    folder.mkdir(parents=True)
    (folder / "app.toml").write_text(toml)
    for name in notebooks:
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('"""A notebook."""\nimport marimo\n')
    return folder
