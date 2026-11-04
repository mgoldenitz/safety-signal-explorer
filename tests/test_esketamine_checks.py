"""Test of 08_esketamine_checks.py on two small hand-made quarters (2025 Q1 and Q2).

Esketamine reports:
  501 Spravato, route blank           -> Spravato or nasal
  502 generic esketamine, nasal route -> Spravato or nasal
  503 generic esketamine, intravenous -> Other route
  601 generic esketamine, no route    -> Route not given (2025 Q2)
  602 Spravato                        -> Spravato or nasal (2025 Q2)
Report 701 has no esketamine.
"""

import importlib.util
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def table(header, rows):
    return "\n".join(["$".join(header) + "$"] + ["$".join(str(v) for v in r) + "$" for r in rows]) + "\n"


DEMO_H = ["primaryid", "caseid", "caseversion", "fda_dt", "init_fda_dt", "age", "age_cod", "sex",
          "occr_country", "rept_cod", "mfr_sndr", "occp_cod", "lit_ref"]
DRUG_H = ["primaryid", "caseid", "drug_seq", "role_cod", "drugname", "prod_ai", "route", "dose_form", "dose_vbm"]


def make_zip(path, yq, demo, drug, reac):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"ASCII/DEMO{yq}.txt", table(DEMO_H, demo))
        z.writestr(f"ASCII/DRUG{yq}.txt", table(DRUG_H, drug))
        z.writestr(f"ASCII/REAC{yq}.txt", table(["primaryid", "caseid", "pt", "drug_rec_act"], reac))
        z.writestr(f"ASCII/OUTC{yq}.txt", table(["primaryid", "caseid", "outc_cod"], []))
        z.writestr(f"ASCII/INDI{yq}.txt", table(["primaryid", "caseid", "indi_drug_seq", "indi_pt"], []))


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("esk")
    raw = tmp / "raw"
    raw.mkdir()
    make_zip(raw / "faers_ascii_2025q1.zip", "25Q1",
        demo=[
            (501, 50, 1, "20250105", "20250105", 40, "YR", "F", "US", "EXP", "JANSSEN", "HP", ""),
            (502, 51, 1, "20250106", "20250106", 40, "YR", "F", "US", "EXP", "JANSSEN", "MD", ""),
            (503, 52, 1, "20250107", "20250107", 40, "YR", "F", "DE", "EXP", "OTHER CO", "MD", "Smith 2025"),
            (701, 70, 1, "20250108", "20250108", 40, "YR", "F", "US", "EXP", "", "CN", ""),
        ],
        drug=[
            (501, 50, 1, "PS", "SPRAVATO", "ESKETAMINE", "", "", ""),
            (502, 51, 1, "PS", "ESKETAMINE", "ESKETAMINE", "Nasal", "", ""),
            (503, 52, 1, "PS", "ESKETAMINE", "ESKETAMINE", "Intravenous (not otherwise specified)", "", ""),
            (701, 70, 1, "PS", "ASPIRIN", "ASPIRIN", "Oral", "", ""),
        ],
        reac=[(501, 50, "Dissociation", ""), (502, 51, "Dissociation", ""),
              (503, 52, "Nausea", ""), (701, 70, "Nausea", "")],
    )
    make_zip(raw / "faers_ascii_2025q2.zip", "25Q2",
        demo=[
            (601, 60, 1, "20250405", "20240305", 40, "YR", "F", "US", "EXP", "JANSSEN", "CN", ""),
            (602, 61, 1, "20250406", "20250406", 40, "YR", "F", "US", "EXP", "JANSSEN", "CN", ""),
        ],
        drug=[
            (601, 60, 1, "PS", "ESKETAMINE", "ESKETAMINE", "", "", ""),
            (602, 61, 1, "SS", "SPRAVATO", "", "", "SPRAY", ""),
        ],
        reac=[(601, 60, "Dissociation", ""), (602, 61, "Sedation", "")],
    )
    dbp = tmp / "test.sqlite"
    out = tmp / "out"
    out.mkdir()
    old = sys.argv
    for name, extra in [("02_load_faers", ["--raw", str(raw)]), ("03_deduplicate", []),
                        ("04_signals", ["--out", str(tmp / "signals.csv")]),
                        ("08_esketamine_checks", ["--raw", str(raw), "--out", str(out)])]:
        sys.argv = [name, "--db", str(dbp)] + extra
        load(name).main()
    sys.argv = old
    return out


def test_route_groups(run):
    s = pd.read_csv(run / "esketamine_route_summary.csv", index_col=0)
    allyrs = s.loc["All years"]
    assert allyrs["Spravato or nasal"] == 3
    assert allyrs["Other route"] == 1
    assert allyrs["Route not given"] == 1


def test_reporters(run):
    r = pd.read_csv(run / "esketamine_reporters.csv", dtype=str)
    q2 = r[(r["quarter"] == "2025Q2") & (r["field"] == "mfr_sndr")]
    assert dict(zip(q2["value"], q2["reports"].astype(int))) == {"JANSSEN": 2}
    first = r[(r["quarter"] == "2025Q2") & (r["field"] == "first_quarter")]
    assert set(first["value"]) == {"2024Q1", "2025Q2"}


def test_subgroup_two_by_two():
    import sqlite3
    con = sqlite3.connect(":memory:")
    # Minimal tables: 4 esketamine reports, 6 others.
    con.executescript("""
        CREATE TABLE report (primaryid INTEGER);
        INSERT INTO report VALUES (1),(2),(3),(4),(5),(6),(7),(8),(9),(10);
        CREATE TABLE reac (primaryid INTEGER, pt_id INTEGER);
        INSERT INTO reac VALUES (1,1),(2,1),(3,1),(5,1),(6,1);
        CREATE TABLE n_pt_all (pt_id INTEGER, n INTEGER); INSERT INTO n_pt_all VALUES (1,5);
        CREATE TABLE n_exposure (exposure TEXT, n INTEGER); INSERT INTO n_exposure VALUES ('esketamine',4);
        CREATE TABLE n_exposure_pt (exposure TEXT, pt_id INTEGER, a INTEGER);
        INSERT INTO n_exposure_pt VALUES ('esketamine',1,3);
    """)
    mod = load("08_esketamine_checks")
    s = mod.subgroup_signals(con, [1, 2], "x").iloc[0]
    # Subgroup 1, 2 (both with term 1); background is the 6 non-esketamine reports, 2 with term 1.
    assert (s.a, s.b, s.c, s.d) == (2, 0, 2, 4)
