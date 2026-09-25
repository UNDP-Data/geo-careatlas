"""Feature tour: a map, interactive charts and UI controls, using synthetic care-work data."""

import marimo

__generated_with = "0.20.1"
app = marimo.App(width="medium", app_title="Feature tour")


@app.cell
def _():
    import altair as alt
    import lonboard
    import marimo as mo
    import numpy as np
    import pandas as pd
    import shapely

    return alt, lonboard, mo, np, pd, shapely


@app.cell
def _(mo):
    mo.md(r"""
    # Feature tour

    A quick check of maps, charts and interactive controls in CareAtlas.
    **All indicator values are synthetic**; only the capital city locations are real.
    """)
    return


@app.cell
def _(np, pd):
    capitals = [
        ("Argentina", "Buenos Aires", "South America", -58.38, -34.60),
        ("Bolivia", "La Paz", "South America", -68.15, -16.50),
        ("Brazil", "Brasília", "South America", -47.88, -15.79),
        ("Chile", "Santiago", "South America", -70.67, -33.45),
        ("Colombia", "Bogotá", "South America", -74.07, 4.71),
        ("Ecuador", "Quito", "South America", -78.47, -0.18),
        ("Paraguay", "Asunción", "South America", -57.58, -25.26),
        ("Peru", "Lima", "South America", -77.04, -12.05),
        ("Uruguay", "Montevideo", "South America", -56.16, -34.90),
        ("Venezuela", "Caracas", "South America", -66.90, 10.48),
        ("Costa Rica", "San José", "Central America", -84.09, 9.93),
        ("El Salvador", "San Salvador", "Central America", -89.19, 13.69),
        ("Guatemala", "Guatemala City", "Central America", -90.51, 14.63),
        ("Honduras", "Tegucigalpa", "Central America", -87.19, 14.07),
        ("Mexico", "Mexico City", "Central America", -99.13, 19.43),
        ("Nicaragua", "Managua", "Central America", -86.25, 12.13),
        ("Panama", "Panama City", "Central America", -79.52, 8.98),
        ("Cuba", "Havana", "Caribbean", -82.37, 23.11),
        ("Dominican Republic", "Santo Domingo", "Caribbean", -69.93, 18.49),
        ("Jamaica", "Kingston", "Caribbean", -76.79, 18.02),
    ]
    rng = np.random.default_rng(seed=42)
    data = pd.DataFrame(capitals, columns=["country", "capital", "region", "lon", "lat"])
    data["women_care_hours"] = rng.uniform(25, 45, len(data)).round(1)
    data["men_care_hours"] = (data["women_care_hours"] * rng.uniform(0.3, 0.6, len(data))).round(1)
    data["care_gap"] = (data["women_care_hours"] - data["men_care_hours"]).round(1)
    data["childcare_coverage"] = rng.uniform(20, 85, len(data)).round(0)
    return (data,)


@app.cell
def _(data, mo):
    indicators = {
        "Weekly unpaid care hours, women": "women_care_hours",
        "Weekly unpaid care hours, men": "men_care_hours",
        "Care gap (women minus men, hours)": "care_gap",
        "Childcare coverage (%)": "childcare_coverage",
    }
    indicator = mo.ui.dropdown(options=indicators, value="Care gap (women minus men, hours)", label="Indicator")
    regions = mo.ui.multiselect(
        options=sorted(data["region"].unique()),
        value=sorted(data["region"].unique()),
        label="Regions",
    )
    minimum = mo.ui.slider(start=0, stop=40, step=1, value=0, label="Minimum value", show_value=True)
    show_map = mo.ui.switch(value=True, label="Show map")
    sort_desc = mo.ui.checkbox(value=True, label="Sort highest first")
    chart_type = mo.ui.radio(options=["Bar", "Scatter"], value="Bar", label="Chart", inline=True)
    return (
        chart_type,
        indicator,
        indicators,
        minimum,
        regions,
        show_map,
        sort_desc,
    )


@app.cell
def _(chart_type, indicator, minimum, mo, regions, show_map, sort_desc):
    mo.vstack([
        mo.md("## Controls"),
        mo.hstack([indicator, regions], justify="start", gap=2),
        mo.hstack([minimum, chart_type], justify="start", gap=2),
        mo.hstack([show_map, sort_desc], justify="start", gap=2),
    ])
    return


@app.cell
def _(data, indicator, minimum, regions, sort_desc):
    column = indicator.value
    filtered = data[data["region"].isin(regions.value) & (data[column] >= minimum.value)]
    filtered = filtered.sort_values(column, ascending=not sort_desc.value).reset_index(drop=True)
    return column, filtered


@app.cell
def _(column, filtered, indicator, indicators, mo):
    label = next(name for name, key in indicators.items() if key == indicator.value)
    mo.hstack([
        mo.stat(value=str(len(filtered)), label="Countries shown"),
        mo.stat(value=f"{filtered[column].mean():.1f}" if len(filtered) else "–", label=f"Average: {label}"),
        mo.stat(value=filtered.iloc[0]["country"] if len(filtered) else "–", label="Top of the list"),
    ], justify="start", gap=2)
    return (label,)


@app.cell
def _(column, filtered, lonboard, mo, np, shapely, show_map):
    def colors(values: np.ndarray) -> np.ndarray:
        """Light to dark UNDP blue, scaled to the values shown."""
        low, high = np.array([187, 222, 251]), np.array([0, 110, 181])
        span = values.max() - values.min() if len(values) and values.max() > values.min() else 1
        share = ((values - values.min()) / span)[:, None] if len(values) else np.zeros((0, 1))
        return (low + share * (high - low)).astype(np.uint8)

    if not show_map.value:
        output = mo.callout("The map is hidden. Turn on 'Show map' to display it.", kind="info")
    elif filtered.empty:
        output = mo.callout("No countries match the current filters.", kind="warn")
    else:
        values = filtered[column].to_numpy(dtype=float)
        points = shapely.points(filtered[["lon", "lat"]].to_numpy())
        output = lonboard.viz(
            points,
            scatterplot_kwargs={
                "get_fill_color": colors(values),
                "get_radius": 40_000 + 60_000 * (values - values.min()) / max(np.ptp(values), 1),
                "radius_units": "meters",
                "stroked": True,
                "get_line_color": [255, 255, 255],
                "line_width_min_pixels": 1,
                "pickable": True,
            },
            map_kwargs={"show_tooltip": True},
        )
    mo.vstack([mo.md("## Map"), output])
    return


@app.cell
def _(alt, chart_type, column, filtered, label, mo):
    if chart_type.value == "Bar":
        chart = alt.Chart(filtered).mark_bar(color="#006eb5").encode(
            x=alt.X(f"{column}:Q", title=label),
            y=alt.Y("country:N", sort=None, title=None),
            tooltip=["country", "capital", alt.Tooltip(f"{column}:Q", title=label)],
        )
    else:
        chart = alt.Chart(filtered).mark_circle(size=120, color="#006eb5").encode(
            x=alt.X("women_care_hours:Q", title="Weekly unpaid care hours, women"),
            y=alt.Y("men_care_hours:Q", title="Weekly unpaid care hours, men"),
            tooltip=["country", "women_care_hours", "men_care_hours"],
        )
    selectable = mo.ui.altair_chart(chart.properties(height=420, width="container"))
    mo.vstack([mo.md("## Chart"), mo.md("Click or drag across the chart to select countries."), selectable])
    return (selectable,)


@app.cell
def _(filtered, mo, selectable):
    selected = selectable.value
    table = mo.ui.table(selected if len(selected) else filtered, selection="multi", page_size=10)
    mo.vstack([
        mo.md(f"## Data ({'selected in chart' if len(selected) else 'all shown'})"),
        table,
    ])
    return (table,)


@app.cell
def _(mo, table):
    rows = table.value
    mo.callout(
        mo.md(f"You ticked **{len(rows)}** row(s): {', '.join(rows['country'])}" if len(rows)
              else "Tick rows in the table above to see them here."),
        kind="neutral",
    )
    return


@app.cell
def _(mo):
    counter = mo.ui.button(value=0, on_click=lambda count: count + 1, label="Click me")
    note = mo.ui.text_area(placeholder="Type something…", label="Notes")
    mo.vstack([
        mo.md("## More controls"),
        mo.ui.tabs({
            "Button": mo.vstack([counter]),
            "Text": mo.vstack([note]),
            "About": mo.md("Tabs, accordions and callouts are layout elements you can combine freely."),
        }),
        mo.accordion({"Show the notebook's purpose": mo.md("Checks that maps, charts and controls work.")}),
    ])
    return counter, note


@app.cell
def _(counter, mo, note):
    mo.md(f"""
    The button was clicked **{counter.value}** time(s). Notes: _{note.value or 'empty'}_
    """)
    return


if __name__ == "__main__":
    app.run()
