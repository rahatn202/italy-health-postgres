"""Italy Health Resources Explorer.

An interactive browser app for the HFA data in data/*.csv.
Run locally with:  streamlit run streamlit_app.py
"""
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
from quality import flag_suspects  # noqa: E402

DATA = ROOT / "data"
REPO_URL = "https://github.com/rahatn202/italy-health-postgres"
MAX_PLACES = 3  # more lines than this can't stay distinguishable for color-blind readers

# Colors: from the project's earthy palette, checked with a palette validator.
# Every pair stays distinguishable with color blindness (protan/deutan/tritan) and
# normal vision. The blue-gray is light (2.06:1), so it always comes with a second cue:
# legend and hover on bars, marker shapes and end labels on lines.
BLUEGRAY, TERRACOTTA, ROSE = "#a0b3b4", "#b27450", "#713d43"
SERIES = [TERRACOTTA, ROSE, BLUEGRAY]   # places on the Trends chart, fixed order
SYMBOLS = ["circle", "square", "diamond"]  # second cue besides color
AREA_COLORS = {"North": BLUEGRAY, "Centre": TERRACOTTA, "South and Islands": ROSE}
AREA_OF = {"Nord-ovest": "North", "Nord-est": "North", "Centro": "Centre",
           "Sud": "South and Islands", "Isole": "South and Islands"}
NEUTRAL = "#6e6a5f"  # Italy benchmark line: warm gray, dashed (5.1:1 contrast)
TEXT = "#1f1d1a"
GRID = "rgba(110,106,95,0.15)"

st.set_page_config(page_title="Italy Health Resources Explorer", page_icon=":hospital:",
                   layout="wide")


def style(fig, height):
    """Shared look for every chart: transparent background, quiet grid, theme font."""
    fig.update_layout(height=height, font_family="Source Sans Pro, sans-serif",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=0, r=10, t=10, b=0),
                      hoverlabel=dict(font_size=13),
                      legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, title=None))
    fig.update_layout(font_color=TEXT)
    fig.update_xaxes(gridcolor=GRID, zeroline=False, tickfont_color=NEUTRAL,
                     title_font_color=NEUTRAL)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont_color=NEUTRAL,
                     title_font_color=NEUTRAL)
    return fig


def fmt(v, measure):
    return f"{v:,.2f}" if measure == "per1000" else f"{v:,.0f}"


# ---------------------------------------------------------------- data
@st.cache_data
def load_data():
    region = pd.read_csv(DATA / "region.csv")
    province = pd.read_csv(DATA / "province.csv", dtype={"province_code": str})
    indicator = pd.read_csv(DATA / "indicator.csv")
    obs = pd.read_csv(DATA / "observation.csv", dtype={"geo_code": str})
    obs = flag_suspects(obs, province)

    # one name table for both levels
    places = pd.concat([
        province.merge(region, on="region_num").assign(
            geo_level="province", geo_code=lambda d: d["province_code"],
            place=lambda d: d["province_name"]),
        region.assign(geo_level="region", geo_code=lambda d: d["region_num"].astype(str),
                      place=lambda d: d["region_name"]),
    ])[["geo_level", "geo_code", "place", "region_name", "macro_area"]]
    obs = obs.merge(places, on=["geo_level", "geo_code"])
    obs["area"] = obs["macro_area"].map(AREA_OF)

    # population joined on, for rates per 1,000 residents
    pop = obs[obs["indicator_id"] == 0][["geo_level", "geo_code", "year", "value"]]
    obs = obs.merge(pop.rename(columns={"value": "population"}),
                    on=["geo_level", "geo_code", "year"], how="left")
    obs["per1000"] = 1000 * obs["value"] / obs["population"]
    obs = obs.merge(indicator[["indicator_id", "short_name", "title_en", "title_it", "unit"]],
                    on="indicator_id")

    # Italy as a whole, from the 20 region totals (only years where all 20 report)
    reg = obs[obs["geo_level"] == "region"]
    italy = (reg.groupby(["short_name", "year"])
                .agg(value=("value", "sum"), population=("population", "sum"),
                     n=("value", "size"))
                .reset_index())
    italy = italy[italy["n"] == 20].drop(columns="n")
    italy["per1000"] = 1000 * italy["value"] / italy["population"]
    return obs, indicator, italy


obs, indicator, italy = load_data()

# ---------------------------------------------------------------- header
st.title("Italy Health Resources Explorer")
st.markdown(
    "Hospital beds, nurses and physicians across Italy's **20 regions** and "
    "**110 provinces**, 1982-2024.  \n"
    ":gray[Source: Istat, *Health for All - Italia* (June 2026).]")

labels = dict(zip(indicator["short_name"], indicator["title_en"]))
with st.container(border=True):
    c1, c2, c3, c4 = st.columns([3, 1.3, 1.3, 1.6], vertical_alignment="center")
    ind = c1.selectbox("Indicator", list(labels), index=1, format_func=labels.get)
    level = c2.radio("Level", ["province", "region"], horizontal=True,
                     format_func=str.capitalize)
    can_rate = ind != "population"
    measure = c3.radio("Measure", ["per1000", "value"] if can_rate else ["value"],
                       horizontal=True,
                       format_func={"per1000": "Per 1,000", "value": "Count"}.get)
    hide_flags = c4.toggle("Hide suspect values", value=True,
                           help="Leave out values that fail the data quality rules "
                                "(see the Data quality tab).")

d = obs[(obs["short_name"] == ind) & (obs["geo_level"] == level)]
if hide_flags:
    d = d[d["flag"] == ""]
d = d.dropna(subset=[measure])
ind_info = indicator.set_index("short_name").loc[ind]
measure_label = "per 1,000 residents" if measure == "per1000" else ind_info["unit"]
ind_it = ind_info["title_it"]
italy_ind = italy[italy["short_name"] == ind].set_index("year")

if d.empty:
    st.warning("No data for this indicator at this level. "
               "SSN nurses are published for regions only.")
    st.stop()

if ind == "phys_registered" and level == "province":
    st.info("Province values before 2011 cover only a few provinces and don't match "
            "the later series. Use 2011 onward.")

tab_rank, tab_trend, tab_data, tab_quality = st.tabs(
    [":material/bar_chart: Ranking", ":material/show_chart: Trends",
     ":material/table: Data", ":material/fact_check: Data quality"])

# ---------------------------------------------------------------- ranking
with tab_rank:
    years = sorted(d["year"].unique())
    r1, r2 = st.columns([3, 2])
    year = r1.select_slider("Year", options=years, value=years[-1])
    regions = sorted(d["region_name"].unique())
    pick_regions = r2.multiselect("Regions", regions, placeholder="All regions") \
        if level == "province" else []

    y = d[d["year"] == year]
    if pick_regions:
        y = y[y["region_name"].isin(pick_regions)]
    y = y.sort_values(measure)
    top, bottom = y.iloc[-1], y.iloc[0]
    italy_val = italy_ind[measure].get(year)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Places with data", f"{len(y)}", border=True)
    m2.metric(f"Highest: {top['place']}", fmt(top[measure], measure), border=True)
    m3.metric(f"Lowest: {bottom['place']}", fmt(bottom[measure], measure), border=True)
    m4.metric("Italy" + (" (all regions)" if measure == "per1000" else " total"),
              fmt(italy_val, measure) if italy_val is not None and pd.notna(italy_val) else "n/a",
              border=True)

    st.markdown(f"**{labels[ind]}**, {measure_label}, {year}")
    fig = px.bar(y, x=measure, y="place", orientation="h", color="area",
                 color_discrete_map=AREA_COLORS,
                 category_orders={"area": list(AREA_COLORS), "place": list(y["place"])},
                 hover_data={"region_name": True, "value": ":,.0f", "per1000": ":.2f",
                             "place": False, measure: False, "area": False},
                 labels={measure: measure_label, "place": "", "region_name": "Region",
                         "value": "Count", "per1000": "Per 1,000", "area": ""})
    fig.update_traces(marker_line_width=0)
    if measure == "per1000" and italy_val is not None and pd.notna(italy_val):
        fig.add_vline(x=italy_val, line_dash="dash", line_color=NEUTRAL, line_width=1.5)
        fig.add_annotation(x=italy_val, y=1, yref="paper", yanchor="bottom",
                           text=f"Italy {italy_val:.2f}", showarrow=False,
                           font=dict(color=NEUTRAL, size=12))
    style(fig, max(380, 17 * len(y) + 90))
    fig.update_layout(bargap=0.3, margin=dict(t=30), yaxis=dict(categoryorder="array",
                                             categoryarray=list(y["place"])))
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------- trends
with tab_trend:
    place_names = sorted(d["place"].unique())
    default = [p for p in ["Roma", "Milano", "Napoli", "Lazio", "Lombardia", "Campania"]
               if p in place_names][:3]
    t1, t2 = st.columns([4, 1], vertical_alignment="bottom")
    chosen = t1.multiselect(f"Compare up to {MAX_PLACES} places", place_names,
                            default=default, max_selections=MAX_PLACES)
    show_italy = t2.toggle("Show Italy", value=True, disabled=measure != "per1000",
                           help="Italy as a whole, from the 20 region totals. "
                                "Available for rates per 1,000.")
    if not chosen:
        st.info("Pick one or more places to compare.")
    else:
        # fill in missing years as empty rows, so the line breaks at a gap
        # instead of drawing a straight line across it
        t = d[d["place"].isin(chosen)]
        full = pd.MultiIndex.from_product(
            [chosen, range(t["year"].min(), t["year"].max() + 1)], names=["place", "year"])
        t = (t.set_index(["place", "year"])[[measure]].reindex(full).reset_index())
        st.markdown(f"**{labels[ind]}**, {measure_label}")
        fig = px.line(t, x="year", y=measure, color="place", symbol="place", markers=True,
                      category_orders={"place": chosen},
                      color_discrete_sequence=SERIES, symbol_sequence=SYMBOLS,
                      labels={measure: measure_label, "year": "", "place": ""})
        fig.update_traces(line_width=2.5, marker_size=9, connectgaps=False)
        # name each line at its last point, so identity never depends on color alone
        end_labels = []  # (y, x, text, color)
        for name in chosen:
            last = t[(t["place"] == name)].dropna(subset=[measure]).tail(1)
            if not last.empty:
                end_labels.append((last[measure].iloc[0], last["year"].iloc[0], name, TEXT))
        if show_italy and measure == "per1000" and not italy_ind.empty:
            it = italy_ind.loc[t["year"].min():t["year"].max(), "per1000"]
            fig.add_scatter(x=it.index, y=it.values, name="Italy", mode="lines",
                            line=dict(color=NEUTRAL, width=2, dash="dash"),
                            hovertemplate="%{y:.2f}")
            if not it.empty:
                end_labels.append((it.values[-1], it.index[-1], "Italy", NEUTRAL))
        # spread labels apart vertically so they never overlap
        if end_labels:
            ys = [v for v, *_ in end_labels]
            all_y = pd.concat([t[measure], pd.Series(ys)]).dropna()
            gap = 0.055 * (all_y.max() - all_y.min() or 1)
            placed = []
            for yv, xv, text, color in sorted(end_labels):
                yv = max(yv, placed[-1] + gap) if placed else yv
                placed.append(yv)
                fig.add_annotation(x=xv, y=yv, text=text, showarrow=False,
                                   xanchor="left", xshift=8, font=dict(color=color, size=12))
        style(fig, 460)
        fig.update_layout(hovermode="x unified", margin=dict(r=110))
        st.plotly_chart(fig, width="stretch")
        st.caption("Gaps in a line are years with no data (or a hidden suspect value). "
                   "The dashed gray line is Italy as a whole. Up to 3 places at a time, so every "
                   "line stays easy to tell apart, including for color-blind readers.")

# ---------------------------------------------------------------- data table
with tab_data:
    all_years = sorted(d["year"].unique())
    v1, v2 = st.columns([3, 2])
    if len(all_years) > 1:
        y_from, y_to = v1.select_slider("Years", options=all_years,
                                        value=(all_years[0], all_years[-1]),
                                        key="data_years")
    else:
        y_from = y_to = all_years[0]
    layout = v2.radio("Layout", ["One row per place and year", "Years as columns"],
                      key="data_layout")
    dy = d[d["year"].between(y_from, y_to)]
    year_text = f"{y_from}" if y_from == y_to else f"{y_from}-{y_to}"
    place_col = level.capitalize()

    if layout == "Years as columns":
        # one row per place, one column per year, showing the chosen measure
        table = (dy.pivot_table(index="place", columns="year", values=measure, aggfunc="first")
                   .reset_index().rename(columns={"place": place_col}))
        table.columns = [str(c) for c in table.columns]
        fmt = "%.2f" if measure == "per1000" else "%,.0f"
        col_config = {c: st.column_config.NumberColumn(format=fmt)
                      for c in table.columns if c != place_col}
        col_config[place_col] = st.column_config.TextColumn(pinned=True)  # stays visible on scroll
        st.caption(f"{labels[ind]} ({ind_it}), {measure_label}, {year_text}. "
                   '"None" means no data for that year.')
    else:
        cols = ["place", "region_name", "macro_area", "year", "value", "population", "per1000"]
        if level == "region":
            cols.remove("region_name")  # the place is the region
        table = (dy[cols]
                 .rename(columns={"place": place_col, "region_name": "Region",
                                  "macro_area": "Macro-area", "year": "Year", "value": "Count",
                                  "population": "Population", "per1000": "Per 1,000"})
                 .sort_values(["Year", place_col]))
        col_config = {"Year": st.column_config.NumberColumn(format="%d"),
                      "Count": st.column_config.NumberColumn(format="%,.0f"),
                      "Population": st.column_config.NumberColumn(format="%,.0f"),
                      "Per 1,000": st.column_config.NumberColumn(format="%.2f")}
        st.caption(f"{labels[ind]} ({ind_it}), {year_text}, {len(table):,} rows")

    st.dataframe(table, width="stretch", hide_index=True, column_config=col_config)
    suffix = "wide" if layout == "Years as columns" else "long"
    st.download_button("Download as CSV", table.to_csv(index=False).encode(),
                       file_name=f"italy_{ind}_{level}_{y_from}_{y_to}_{suffix}.csv",
                       mime="text/csv")

# ---------------------------------------------------------------- quality
with tab_quality:
    st.markdown(
        "Two rules flag suspect **province** values (the same rules as the "
        "`suspect_observation` view in the SQL database):\n"
        "- **province_sum_mismatch**: all provinces in a region reported, but they add up "
        "to more than 5% away from Istat's region total\n"
        "- **isolated_spike**: the value jumps more than 40% from both the year before "
        "and the year after")

    flagged = obs[(obs["flag"] != "") & (obs["short_name"] == ind)]
    q1, q2 = st.columns(2)
    q1.metric("Suspect values, this indicator", f"{len(flagged)}")
    q2.metric("Suspect values, all indicators", f"{(obs['flag'] != '').sum()}")

    if flagged.empty:
        st.success("No suspect values for this indicator.")
    else:
        st.dataframe(
            flagged[["place", "region_name", "year", "value", "flag"]]
            .rename(columns={"place": "Province", "region_name": "Region", "year": "Year",
                             "value": "Reported value", "flag": "Rule"})
            .sort_values(["Year", "Province"]),
            width="stretch", hide_index=True,
            column_config={"Year": st.column_config.NumberColumn(format="%d"),
                           "Reported value": st.column_config.NumberColumn(format="%,.0f")})
        if ind == "phys_registered":
            st.caption("Example: in 2014 Perugia reports about 37,000 registered physicians, "
                       "while the whole Umbria region reports 6,400. The 2014 province values "
                       "appear to be shuffled between provinces in the source file.")

    st.subheader("Coverage")
    cov = (obs[obs["short_name"] == ind].groupby("geo_level")
           .agg(first_year=("year", "min"), last_year=("year", "max"),
                places=("geo_code", "nunique"), values=("value", "size"))
           .reset_index().assign(geo_level=lambda x: x["geo_level"].str.capitalize())
           .rename(columns={"geo_level": "Level", "first_year": "First year",
                                          "last_year": "Last year", "places": "Places",
                                          "values": "Values"}))
    st.dataframe(cov, hide_index=True,
                 column_config={"First year": st.column_config.NumberColumn(format="%d"),
                                "Last year": st.column_config.NumberColumn(format="%d"),
                               "Values": st.column_config.NumberColumn(format="%,d")})

# ---------------------------------------------------------------- footer
st.divider()
st.caption(f"Built by Rahat Naseem with Python, PostgreSQL and Streamlit. "
           f"Code and SQL: [{REPO_URL.removeprefix('https://')}]({REPO_URL}). "
           "Data: Istat, Health for All - Italia (June 2026).")
