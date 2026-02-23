"""
 This notebok allows exploring global poverty patterns at various spatial scales
"""

import marimo

__generated_with = "0.20.1"
app = marimo.App(width="medium", auto_download=["html"])


@app.cell
def menu():
    import marimo as mo
    import os
    from careatlas.app.repo import sidebar_content
    import marimo as mo

    mo.sidebar(sidebar_content)
    #render_modal()



    #mine = {(k,v) for k, v in os.environ.items() if k.startswith('GIT')}
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


if __name__ == "__main__":
    app.run()
