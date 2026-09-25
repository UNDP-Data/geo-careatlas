import json

import pytest

from careatlas.app.uploads import (
    MAX_UPLOAD_BYTES,
    UploadError,
    check_marimo_source,
    notebook_name_for,
    save_to_workspace,
    to_marimo,
)

MARIMO_NOTEBOOK = '''import marimo

app = marimo.App()


@app.cell
def _():
    x = 1
    return (x,)
'''


def jupyter_notebook(*sources: str) -> bytes:
    cells = [{"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": [s]}
             for s in sources]
    return json.dumps({"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}).encode()


def test_marimo_notebook_is_accepted_unchanged():
    assert to_marimo("analysis.py", MARIMO_NOTEBOOK.encode()) == MARIMO_NOTEBOOK


def test_jupyter_notebook_is_converted_to_marimo():
    source = to_marimo("analysis.ipynb", jupyter_notebook("import math", "radius = 2\narea = math.pi * radius ** 2"))
    check_marimo_source(source)
    assert "area = math.pi * radius ** 2" in source


def test_conversion_does_not_run_the_notebook(tmp_path):
    marker = tmp_path / "ran.txt"
    to_marimo("sneaky.ipynb", jupyter_notebook(f"open({str(marker)!r}, 'w').write('ran')"))
    assert not marker.exists()


@pytest.mark.parametrize(("filename", "data", "message"), [
    ("script.py", b"print('hello')\n", "not a marimo notebook"),
    ("broken.py", b"def (:\n", "not valid Python"),
    ("data.csv", b"a,b\n1,2\n", "Upload a marimo notebook"),
    ("empty.py", b"   \n", "empty"),
    ("bad.ipynb", b"{not json", "not a valid Jupyter notebook"),
    ("other.ipynb", b'{"no": "cells"}', "not a valid Jupyter notebook"),
    ("big.py", b"#" * (MAX_UPLOAD_BYTES + 1), "larger than"),
])
def test_invalid_uploads_are_rejected(filename, data, message):
    with pytest.raises(UploadError, match=message):
        to_marimo(filename, data)


@pytest.mark.parametrize(("filename", "expected"), [
    ("Poverty Map (v2).ipynb", "poverty_map_v2"),
    ("2023_survey.py", "notebook_2023_survey"),
    ("!!!.py", "notebook"),
])
def test_notebook_names_are_derived_from_the_file_name(filename, expected):
    assert notebook_name_for(filename) == expected


def test_existing_notebooks_are_only_replaced_when_asked(tmp_path):
    save_to_workspace(tmp_path, "analysis", "first")
    with pytest.raises(FileExistsError):
        save_to_workspace(tmp_path, "analysis", "second")
    save_to_workspace(tmp_path, "analysis", "second", overwrite=True)
    assert (tmp_path / "analysis.py").read_text() == "second"
    assert [p.name for p in tmp_path.iterdir()] == ["analysis.py"]


def test_unsafe_names_are_rejected(tmp_path):
    with pytest.raises(UploadError):
        save_to_workspace(tmp_path, "../outside", MARIMO_NOTEBOOK)
