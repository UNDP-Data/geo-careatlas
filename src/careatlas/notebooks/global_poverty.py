"""
 This notebok allows exploring global poverty patterns at various spatial scales
"""

import marimo

__generated_with = "0.19.11"
app = marimo.App()


@app.cell
def _():
    import marimo as mo
    mo.md("# Hello from marimo 👋")
    return (mo,)


@app.cell
def _(mo):
    metric = mo.ui.dropdown(
        options=["Population", "Facilities", "Coverage"],
        value="Population",
        label="Metric",
    )
    threshold = mo.ui.slider(start=0, stop=100, value=30, label="Threshold")
    mo.vstack([metric, threshold])
    return


@app.cell
def _(mo):
    request = mo.app_meta().request

    if request is not None:
        # This will display a nice JSON/Table of all incoming headers
        mo.output.replace(mo.md(f"### Incoming Headers\n{list(request.headers)}"))
    else:
        mo.md("No active request found (are you in the editor?)")
    return


if __name__ == "__main__":
    app.run()
