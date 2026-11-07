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
BLUE = "#2a78d6"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]  # fixed order
MAX_PLACES = 5

st.set_page_config(page_title="Italy Health Resources Explorer", layout="wide")


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

    # population joined on, for rates per 1,000 residents
    pop = obs[obs["indicator_id"] == 0][["geo_level", "geo_code", "year", "value"]]
    obs = obs.merge(pop.rename(columns={"value": "population"}),
                    on=["geo_level", "geo_code", "year"], how="left")
    obs["per1000"] = 1000 * obs["value"] / obs["population"]
    obs = obs.merge(indicator[["indicator_id", "short_name", "title_en", "title_it"]],
                    on="indicator_id")
    return obs, indicator


obs, indicator = load_data()

# ---------------------------------------------------------------- controls
st.title("Italy Health Resources Explorer")
st.caption("Hospital beds, nurses and physicians for Italy's 20 regions and 110 provinces. "
           "Source: Istat, Health for All - Italia (June 2026).")

labels = dict(zip(indicator["short_name"], indicator["title_en"]))
c1, c2, c3, c4 = st.columns([3, 1.3, 1.3, 1.6])
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
measure_label = "per 1,000 residents" if measure == "per1000" else \
    indicator.set_index("short_name").loc[ind, "unit"]
ind_it = indicator.set_index("short_name").loc[ind, "title_it"]

if d.empty:
    st.warning("No data for this indicator at this level. "
               "SSN nurses are published for regions only.")
    st.stop()

if ind == "phys_registered" and level == "province":
    st.info("Province values before 2011 cover only a few provinces and don't match "
            "the later series. Use 2011 onward.")

tab_rank, tab_trend, tab_data, tab_quality = st.tabs(
    ["Ranking", "Trends", "Data", "Data quality"])

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

    m1, m2, m3 = st.columns(3)
    top, bottom = y.iloc[-1], y.iloc[0]
    m1.metric("Places with data", f"{len(y)}")
    m2.metric(f"Highest: {top['place']}", f"{top[measure]:,.2f}" if measure == "per1000"
              else f"{top[measure]:,.0f}")
    m3.metric(f"Lowest: {bottom['place']}", f"{bottom[measure]:,.2f}" if measure == "per1000"
              else f"{bottom[measure]:,.0f}")

    fig = px.bar(y, x=measure, y="place", orientation="h",
                 hover_data={"region_name": True, "value": ":,.0f",
                             "per1000": ":.2f", "place": False, measure: False},
                 labels={measure: measure_label, "place": "", "region_name": "Region",
                         "value": "Count", "per1000": "Per 1,000"})
    fig.update_traces(marker_color=BLUE, marker_line_width=0)
    fig.update_layout(height=max(360, 18 * len(y) + 80), bargap=0.25,
                      margin=dict(l=0, r=10, t=30, b=0),
                      title=dict(text=f"{labels[ind]}, {year}", font_size=15),
                      xaxis=dict(gridcolor="rgba(128,128,128,0.15)"))
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------- trends
with tab_trend:
    place_names = sorted(d["place"].unique())
    default = [p for p in ["Roma", "Milano", "Napoli", "Lazio", "Lombardia", "Campania"]
               if p in place_names][:3]
    chosen = st.multiselect(f"Compare up to {MAX_PLACES} places", place_names,
                            default=default, max_selections=MAX_PLACES)
    if not chosen:
        st.info("Pick one or more places to compare.")
    else:
        # fill in missing years as empty rows, so the line breaks at a gap
        # instead of drawing a straight line across it
        t = d[d["place"].isin(chosen)]
        full = pd.MultiIndex.from_product(
            [chosen, range(t["year"].min(), t["year"].max() + 1)], names=["place", "year"])
        t = (t.set_index(["place", "year"])[[measure]].reindex(full).reset_index())
        fig = px.line(t, x="year", y=measure, color="place", markers=True,
                      category_orders={"place": chosen},
                      color_discrete_sequence=SERIES,
                      labels={measure: measure_label, "year": "", "place": ""})
        fig.update_traces(line_width=2, marker_size=7)
        fig.update_traces(connectgaps=False)
        fig.update_layout(hovermode="x unified", height=460,
                          margin=dict(l=0, r=10, t=40, b=0),
                          title=dict(text=labels[ind], font_size=15),
                          legend=dict(orientation="h", yanchor="top", y=-0.08, x=0),
                          yaxis=dict(gridcolor="rgba(128,128,128,0.15)"))
        st.plotly_chart(fig, width="stretch")
        st.caption("Gaps in a line are years with no data (or a hidden suspect value).")

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
