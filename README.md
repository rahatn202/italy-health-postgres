# Italy Health Resources Database (PostgreSQL)

A relational database of hospital beds, nurses and physicians for Italy's 20 regions and 110 provinces, built from Istat's *Health for All – Italia* (HFA) release of June 2026. The project covers the full path from a proprietary, Windows-only binary format to a validated PostgreSQL schema with quality checks and analysis queries.

## Why this project

Istat distributes HFA as a Windows viewer program. The data cannot be exported on macOS or Linux, and there is no documented file format. This project:

1. **Reads the binary files directly** (`src/hfa_reader.py`). The format was worked out from the raw bytes and confirmed by matching file sizes exactly and by checking results against published figures (for example, Italy's resident population is 56.98M in 2001 and 58.98M in 2023).
2. **Loads them into a normalized PostgreSQL schema** with primary keys, foreign keys and check constraints.
3. **Validates the data with SQL**: coverage, time-series gaps, province totals against region totals, and year-over-year outliers. These checks found real errors in the source (see [Findings](#data-quality-findings)).
4. **Provides analysis-ready views and example queries** that use joins, CTEs, window functions and conditional aggregation.

## Data

| Indicator | HFA code | Levels | Years |
|---|---|---|---|
| Resident population | 0 | province, region | 1982–2024 |
| Ordinary hospital beds (public + accredited private) | 7210 | province, region | 1990–2023 |
| Nursing staff in public and accredited private hospitals | 9122 | province, region | 1990–2023 |
| Nursing staff employed by the national health service (SSN) | 9102 | region* | 1994–2024 |
| Physicians enrolled in the provincial register | 9180 | province, region | 2011–2024 (reliable) |
| Practising specialist physicians | 9240 | province, region | 2011–2024 |

\* At province level, only the autonomous provinces of Bolzano and Trento report this series. Those two provinces are NUTS-2 regions in their own right.

Source: Istat, *Health for All – Italia*, June 2026. Istat releases its data under a Creative Commons Attribution license; check Istat's current terms before reusing the data.

## Schema

```
region (region_num PK, region_name, macro_area)
   │ 1
   │ n
province (province_code PK, province_name, region_num FK)

indicator (indicator_id PK, short_name, title_it, title_en, unit, hfa_group)

observation (observation_id PK,
             province_code FK NULL, region_num FK NULL,   -- exactly one is set
             indicator_id FK, year, value)
```

- `observation` is a long (tidy) fact table. A CHECK constraint ensures each row belongs to exactly one geography, and partial unique indexes prevent duplicate geography × indicator × year rows.
- Missing values are absent rows, not sentinels. The HFA sentinel `-1e8` is removed during export.

### Views (`sql/03_views.sql`)

| View | Purpose |
|---|---|
| `suspect_observation` | Province values that fail a quality rule, with the reason |
| `province_panel` | Wide province × year panel, one column per indicator, with suspect values excluded |
| `province_rates` | The same panel as rates per 1,000 residents |
| `region_panel` | Wide region × year panel, including the region-only SSN nurses series |

## Repository layout

```
src/hfa_reader.py         reader for the HFA binary format (documented in the docstring)
src/export_csv.py         writes the tidy CSVs in data/
src/quality.py            data quality rules in pandas (used by the app)
streamlit_app.py          interactive browser explorer
data/*.csv                exported data (so the database can be built without HFA)
sql/01_schema.sql         tables, keys, constraints, indexes
sql/02_load.sql           staged COPY load
sql/03_views.sql          quality-flag and panel views
sql/04_quality_checks.sql coverage, gaps, province-vs-region validation, outliers
sql/05_analysis.sql       example analyses
run_all.sh                builds everything
```

## Running it

Requirements: PostgreSQL 13+ and, to regenerate the CSVs, Python 3.9+ with pandas and numpy.

```bash
# build from the included CSVs
./run_all.sh

# or regenerate the CSVs from a fresh HFA download first
pip install -r requirements.txt
./run_all.sh /path/to/HFA/Data

psql -d italy_health -f sql/04_quality_checks.sql
psql -d italy_health -f sql/05_analysis.sql
```

## Interactive explorer

`streamlit_app.py` is a browser app for exploring the data without SQL:

- **Ranking**: provinces or regions ranked for any year, as counts or per 1,000 residents, with a region filter
- **Trends**: compare up to five places over time; years with no data show as gaps in the line
- **Data**: the filtered table, with a CSV download
- **Data quality**: the values flagged as suspect, and the coverage of each indicator

The quality rules live in `src/quality.py`. They are the same rules as the `suspect_observation` view, and they flag the same 122 values.

Run it locally:

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Data quality findings

The checks in `sql/04_quality_checks.sql` found these problems in the source data:

- **Physicians on the register, 2014 (province level):** values are shuffled between provinces. For example, province Perugia shows 37,038 physicians, which is Rome's level, while the whole Umbria region has 6,400. Province sums miss region totals by up to 500%. 96 of the 2014 province values are flagged and excluded from `province_panel`.
- **Physicians on the register before 2011:** only a few provinces report, and the values do not match the later series. Region totals start in 2011, so the series is treated as reliable from 2011.
- **Sardinia:** HFA lists 8 provinces from before the 2016 reorganization. In recent years only 4 of them have data, and they cover about 79% of the region's population. Province-level comparisons within Sardinia are therefore unreliable.
- **Gaps:** the 5 Calabrian provinces have no 2020 bed data, the Lazio provinces have no data for 1991–1995, and Sardinian specialist physician data are missing for 2017–2019.
- **One-year spikes:** a few bed and nurse counts jump by more than 40% and return to normal the next year (for example, Vibo Valentia beds in 2003). These are flagged as `isolated_spike`.

## Example results

Ordinary hospital beds per 1,000 residents fell in every macro-area between 2013 and 2023. The drop was steepest in the North, which started from a higher level. In 2023, the rate ranges from 3.60 in Emilia-Romagna to 2.35 in Campania (query A1).

## Possible extensions

- Add NUTS-3 codes through a crosswalk table, handling the Sardinia reorganizations of 2016 and 2021.
- Add automated tests (pytest for the reader, plus SQL assertions run in CI).
- Package it as a Docker Compose setup so the database starts with one command.
