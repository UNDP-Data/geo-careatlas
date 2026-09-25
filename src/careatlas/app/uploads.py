"""Uploading notebooks into an editor's workspace.

Accepts marimo notebooks (.py) and Jupyter notebooks (.ipynb). Jupyter notebooks
are converted with ``marimo convert``, which rewrites the source and strips
outputs without running any code. Uploaded code is never imported or executed
here: .py files are checked by parsing them.

Uploads land in the uploader's own worktree as an uncommitted change, like any
edit, so nothing is shared until they commit.
"""

import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from careatlas.app.editor import notebook_env
from careatlas.app.manage import NOTEBOOK_PATTERN, slugify

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
CONVERT_TIMEOUT = 60
EXTENSIONS = (".py", ".ipynb")


class UploadError(ValueError):
    """An upload that cannot be accepted. The message is safe to show to users."""


def notebook_name_for(filename: str) -> str:
    """File name (without .py) for an uploaded notebook, e.g. "Poverty Map (v2).ipynb" -> "poverty_map_v2"."""
    name = slugify(Path(filename).stem)
    if not name:
        return "notebook"
    return name if NOTEBOOK_PATTERN.match(name) else f"notebook_{name}"


def _is_app_call(node: ast.AST) -> bool:
    """``marimo.App(...)`` or ``App(...)``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Attribute) and func.attr == "App") or (isinstance(func, ast.Name) and func.id == "App")


def _is_cell_decorator(node: ast.AST) -> bool:
    """``@app.cell``, ``@app.cell(...)`` or ``@app.function``."""
    target = node.func if isinstance(node, ast.Call) else node
    return isinstance(target, ast.Attribute) and target.attr in ("cell", "function")


def check_marimo_source(source: str) -> None:
    """Raise UploadError unless the source parses as a marimo notebook."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise UploadError(f"The notebook is not valid Python (line {exc.lineno}: {exc.msg})") from exc
    has_app = any(isinstance(node, ast.Assign) and _is_app_call(node.value) for node in tree.body)
    has_cell = any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_is_cell_decorator(d) for d in node.decorator_list)
        for node in tree.body
    )
    if not (has_app and has_cell):
        raise UploadError("This .py file is not a marimo notebook. Upload a marimo notebook or a Jupyter .ipynb file")


def _convert_ipynb(data: bytes) -> str:
    try:
        notebook = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UploadError("This .ipynb file is not a valid Jupyter notebook") from exc
    if not isinstance(notebook, dict) or not isinstance(notebook.get("cells"), list):
        raise UploadError("This .ipynb file is not a valid Jupyter notebook")

    with tempfile.TemporaryDirectory(prefix="careatlas-upload-") as folder:
        source, target = Path(folder) / "upload.ipynb", Path(folder) / "upload.py"
        source.write_bytes(data)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "marimo", "-q", "-y", "convert", str(source), "-o", str(target)],
                cwd=folder, env=notebook_env(), capture_output=True, text=True, timeout=CONVERT_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            raise UploadError("Converting the notebook took too long") from exc
        if result.returncode != 0 or not target.is_file():
            raise UploadError("The Jupyter notebook could not be converted to marimo")
        return target.read_text(encoding="utf-8")


def to_marimo(filename: str, data: bytes) -> str:
    """Validate an upload and return it as marimo notebook source."""
    extension = Path(filename).suffix.lower()
    if extension not in EXTENSIONS:
        raise UploadError("Upload a marimo notebook (.py) or a Jupyter notebook (.ipynb)")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError(f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    if not data.strip():
        raise UploadError("The file is empty")

    if extension == ".ipynb":
        source = _convert_ipynb(data)
    else:
        try:
            source = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UploadError("The file is not UTF-8 text") from exc
    check_marimo_source(source)
    return source


def save_to_workspace(folder: Path, name: str, source: str, overwrite: bool = False) -> Path:
    """Write the notebook into the editor's app folder. Raises FileExistsError unless overwriting."""
    if not NOTEBOOK_PATTERN.match(name):
        raise UploadError("Use lowercase letters, digits and '_' for the notebook name, starting with a letter")
    path = folder / f"{name}.py"
    if path.exists() and not overwrite:
        raise FileExistsError(path.name)
    temporary = path.with_name(f".{path.name}.upload")
    temporary.write_text(source, encoding="utf-8")
    os.replace(temporary, path)
    return path
