"""Export the health-resource indicators from HFA to tidy CSVs for PostgreSQL.

Usage: python src/export_csv.py <path to HFA/Data> <output dir>

Writes:
  region.csv       20 regions (HFA region number, name, macro-area)
  province.csv     110 provinces (HFA unit code, name, region)
  indicator.csv    the selected indicators with Italian and English labels
  observation.csv  long table: geo_level, geo_code, indicator_id, year, value
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import hfa_reader as hfa  # noqa: E402

# indicator id -> (short name, English label, unit of measure)
INDICATORS = {
    0:    ("population",       "Resident population, both sexes", "persons"),
    7210: ("beds",             "Ordinary (overnight) hospital beds, public and accredited private hospitals", "beds"),
    9122: ("nurses_hosp",      "Nursing staff in public and accredited private hospitals", "persons"),
    9102: ("nurses_ssn",       "Nursing staff employed by the national health service (SSN)", "persons"),
    9180: ("phys_registered",  "Physicians enrolled in the provincial medical register", "persons"),
    9240: ("phys_spec_active", "Practising specialist physicians (excl. GPs and family paediatricians)", "persons"),
}

MACRO = {  # Istat macro-areas (ripartizioni) by HFA region number
    **{r: "Nord-ovest" for r in (1, 2, 3, 7)},
    **{r: "Nord-est" for r in (4, 5, 6, 8)},
    **{r: "Centro" for r in (9, 10, 11, 12)},
    **{r: "Sud" for r in (13, 14, 15, 16, 17, 18)},
    **{r: "Isole" for r in (19, 20)},
}


def main(data_dir: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    ids = set(INDICATORS)

    # indicators
    titles = hfa.read_indicators(data_dir).set_index("indicator_id")
    ind = pd.DataFrame([
        {"indicator_id": i, "short_name": s, "title_it": titles.loc[i, "title_it"],
         "title_en": en, "unit": u, "hfa_group": titles.loc[i, "group_title"]}
        for i, (s, en, u) in INDICATORS.items()])

    # regions come from the national file (first 20 units)
    nat_units, _ = hfa.read_units(data_dir, "10000")
    regions = nat_units.iloc[:20].reset_index(drop=True)
    region = pd.DataFrame({"region_num": range(1, 21), "region_name": regions["unit_name"]})
    region["macro_area"] = region["region_num"].map(MACRO)

    # provinces come from the 20 regional files
    prov_rows, obs = [], []
    for rnum in range(1, 21):
        fid = f"1{rnum:02d}00"
        units, _ = hfa.read_units(data_dir, fid)
        is_total = units["unit_name"].str.isupper()
        if is_total.sum() != 1:
            raise ValueError(f"{fid}: expected one region-total unit")
        for _, u in units[~is_total].iterrows():
            prov_rows.append({"province_code": u["unit_code"], "province_name": u["unit_name"],
                              "region_num": rnum})
        v = hfa.read_values(data_dir, fid, ids)
        v = v[v["unit_code"].isin(units.loc[~is_total, "unit_code"])]
        obs.append(v.assign(geo_level="province", geo_code=v["unit_code"]))
    province = pd.DataFrame(prov_rows)

    # region-level values from the national file (needed for region-only
    # indicators such as nurses_ssn, and to validate province sums)
    v = hfa.read_values(data_dir, "10000", ids)
    code2num = dict(zip(regions["unit_code"], region["region_num"]))
    v = v[v["unit_code"].isin(code2num)]
    obs.append(v.assign(geo_level="region", geo_code=v["unit_code"].map(code2num).astype(str)))

    obs = pd.concat(obs, ignore_index=True)[["geo_level", "geo_code", "indicator_id", "year", "value"]]
    obs = obs.sort_values(["geo_level", "indicator_id", "geo_code", "year"])

    region.to_csv(out / "region.csv", index=False)
    province.to_csv(out / "province.csv", index=False)
    ind.to_csv(out / "indicator.csv", index=False)
    obs.to_csv(out / "observation.csv", index=False)
    print(f"{len(region)} regions, {len(province)} provinces, {len(ind)} indicators, "
          f"{len(obs):,} observations -> {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
