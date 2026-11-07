"""Read the Istat "Health for All - Italia" (HFA) database without Windows.

Background
----------
Istat publishes HFA as a Windows program (HFA.exe) plus a folder of data
files. The program can only be used on Windows, and Istat does not explain
how the data files are organized. This module reads the data files
directly, so the data can be used on any computer (Mac, Linux or Windows)
and loaded into pandas or a database.

Istat does not publish the file layout described below. I worked it out
by examining the June 2026 files, and checked it in two ways:
  1. File sizes: each yearly data file is exactly
     (number of indicators) x (number of places) x 4 bytes.
  2. Known figures: the values read out match Istat's published totals,
     for example Italy's resident population (56.98 million in 2001,
     58.98 million in 2023).

How the files are organized
---------------------------
All files are in the HFA "Data" folder. Text is stored in the old Windows
encoding cp1252, which is needed for Italian letters such as a-grave and
e-grave to display correctly. Numbers are stored in Windows byte order
(little-endian).

  mainlist.ind
      The names of all indicators. They are arranged like a book:
      10 groups (topics such as population or health care), each with
      100 pages. Each page holds one main title and up to 9 sub-titles,
      each in a 128-byte text box. An indicator's ID comes from its
      position:  ID = group*1000 + page*10 + slot,
      where slot 0 is the main title and slots 1-9 are the sub-titles.
      Example: ID 7210 = group 7, page 21, slot 0 = hospital beds.

  mainlist.grp
      The names of the 10 groups.

  XXXXX.rid
      The codes of the places in file set XXXXX (provinces or regions),
      one code per 16-byte text box.

  XXXXX.par
      The names of those places, in the same order as the codes in .rid
      (each name in a 64-byte text box). The names may be split across
      more than one list. At the end is the list of years the file covers.

  XXXXX.ind
      The indicator IDs stored in this file set, in the order they appear
      as rows in the yearly data files.

  XXXXX.YYYY   (for example 10900.2023)
      The data for one year. It is a table of decimal numbers (4 bytes
      each) with one row per indicator (order from .ind) and one column
      per place (order from .rid). Rows are stored one after another.
      The value -100,000,000 (-1e8) means the data is missing.

Which file set holds which places
---------------------------------
  10000          National file: the 20 regions, Italy as a whole, and the
                 macro-areas (North-West, North-East, Centre, South, Islands).
  10100 - 12000  One file set per region (10100 = Piemonte, 10900 = Toscana,
                 ... 12000 = Sardegna). Each contains that region's provinces
                 plus the region total, whose name is written in capital
                 letters (for example "TOSCANA").

Main functions
--------------
  read_indicators(data_dir)        table of all indicator IDs and titles
  read_units(data_dir, file_id)    places (codes and names) and years
  read_values(data_dir, file_id)   long table of values:
                                   place, indicator, year, value
  file_ids(data_dir)               list of all file sets in the folder
Note: this layout was checked on the June 2026 release only. If Istat
   changes the format in a later release, the checks above should be run
   again.
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pandas as pd

MISSING = -1e8



def _str(b: bytes) -> str:
    return b.split(b"\0")[0].decode("cp1252").strip()


def read_indicators(data_dir: Path) -> pd.DataFrame:
    """Indicator id, group, parent title and indicator title."""
    b = (data_dir / "mainlist.ind").read_bytes()
    R = struct.unpack("<H", b[3:5])[0]
    o, rows = 5, []
    for g in range(10):
        o += 2  # used-page count (all 100 page slots are stored anyway)
        for p in range(100):
            pid = g * 1000 + p * 10
            parent = _str(b[o:o + R]); o += R
            o += 2  # child count
            if parent:
                rows.append((pid, g, parent, parent))
            for c in range(9):
                child = _str(b[o:o + R]); o += R
                if child:
                    rows.append((pid + 1 + c, g, parent, child))
    if o != len(b):
        raise ValueError(f"mainlist.ind parsed to byte {o}, file has {len(b)}")
    grp = (data_dir / "mainlist.grp").read_bytes()
    gR = struct.unpack("<H", grp[3:5])[0]
    groups = [_str(grp[5 + i * gR:5 + (i + 1) * gR]) for i in range(10)]
    df = pd.DataFrame(rows, columns=["indicator_id", "group_id", "parent_title", "title_it"])
    df["group_title"] = df["group_id"].map(dict(enumerate(groups)))
    return df


def read_units(data_dir: Path, file_id: str) -> tuple[pd.DataFrame, list[int]]:
    """Units (code, name) of one file set, plus its year list."""
    rid = (data_dir / f"{file_id}.rid").read_bytes()
    codes = [_str(rid[i:i + 16]) for i in range(0, len(rid), 16)]
    b = (data_dir / f"{file_id}.par").read_bytes()
    R = struct.unpack("<H", b[3:5])[0]
    o, names = 5, []
    while len(names) < len(codes):
        n = struct.unpack("<H", b[o:o + 2])[0]; o += 2
        names += [_str(b[o + i * R:o + (i + 1) * R]) for i in range(n)]; o += n * R
    while True:  # skip any empty trailing lists before the year block
        n = struct.unpack("<H", b[o:o + 2])[0]
        if len(b) - o == 2 + 2 * n:
            break
        o += 2 + n * R
    years = list(struct.unpack(f"<{n}H", b[o + 2:o + 2 + 2 * n]))
    if len(names) != len(codes):
        raise ValueError(f"{file_id}: {len(codes)} codes but {len(names)} names")
    return pd.DataFrame({"file_id": file_id, "unit_code": codes, "unit_name": names}), years


def read_values(data_dir: Path, file_id: str, indicator_ids=None) -> pd.DataFrame:
    """Long table (file_id, unit_code, indicator_id, year, value); missing dropped."""
    units, years = read_units(data_dir, file_id)
    ib = (data_dir / f"{file_id}.ind").read_bytes()
    n_ind = struct.unpack("<H", ib[:2])[0]
    ids = np.frombuffer(ib, "<u2", n_ind, offset=2).astype(int)
    keep = np.ones(n_ind, bool) if indicator_ids is None else np.isin(ids, list(indicator_ids))
    out = []
    for y in years:
        f = data_dir / f"{file_id}.{y}"
        if not f.exists():
            continue
        grid = np.fromfile(f, "<f4").reshape(n_ind, len(units))[keep]
        r, c = np.nonzero(grid > MISSING / 2)
        out.append(pd.DataFrame({
            "file_id": file_id,
            "unit_code": units["unit_code"].to_numpy()[c],
            "indicator_id": ids[keep][r],
            "year": y,
            "value": grid[r, c].astype(float),
        }))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def file_ids(data_dir: Path) -> list[str]:
    return sorted(p.stem for p in data_dir.glob("*.rid"))
