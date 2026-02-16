import marimo

__generated_with = "0.19.9"
app = marimo.App()


@app.cell
def _():
    import marimo as mo
    mo.md("# Hello from marimo 👋")
    
@app.cell
def _(mo):
    metric = mo.ui.dropdown(
        options=["Population", "Facilities", "Coverage"],
        value="Population",
        label="Metric",
    )
    threshold = mo.ui.slider(start=0, stop=100, value=30, label="Threshold")
    mo.vstack([metric, threshold])