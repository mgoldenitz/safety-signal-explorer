"""End-to-end test on two small hand-made FAERS quarters.

The fixture is built so every count can be checked by hand:
  - case 10 has two versions; only version 2 (primaryid 102) is kept
  - case 99 is on the FDA deleted list and is dropped
  - a concomitant (role C) esketamine row does not count as exposure
"""

import importlib.util
import io
import math
import sqlite3
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import common  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def table(header, rows):
    lines = ["$".join(header) + "$"] + ["$".join(str(v) for v in r) + "$" for r in rows]
    return "\n".join(lines) + "\n"


def make_zip(path, yq, demo, drug, reac, outc, indi, deleted=None):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"ASCII/DEMO{yq}.txt", table(
            ["primaryid", "caseid", "caseversion", "fda_dt", "age", "age_cod", "sex", "occr_country", "rept_cod"], demo))
        z.writestr(f"ASCII/DRUG{yq}.txt", table(
            ["primaryid", "caseid", "drug_seq", "role_cod", "drugname", "prod_ai"], drug))
        z.writestr(f"ASCII/REAC{yq}.txt", table(["primaryid", "caseid", "pt", "drug_rec_act"], reac))
        z.writestr(f"ASCII/OUTC{yq}.txt", table(["primaryid", "caseid", "outc_cod"], outc))
        z.writestr(f"ASCII/INDI{yq}.txt", table(["primaryid", "caseid", "indi_drug_seq", "indi_pt"], indi))
        if deleted:
            z.writestr(f"Deleted/DELETED_CASES_{yq}.txt", "\n".join(str(d) for d in deleted) + "\n")


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ssx")
    raw = tmp / "raw"
    raw.mkdir()
    # Quarter 1: case 10 version 1, plus cases 20 to 26
    make_zip(raw / "faers_ascii_2019q1.zip", "19Q1",
        demo=[
            (101, 10, 1, "20190105", 40, "YR", "F", "US", "EXP"),
            (201, 20, 1, "20190110", 35, "YR", "M", "US", "EXP"),
            (211, 21, 1, "20190111", 50, "YR", "F", "US", "EXP"),
            (221, 22, 1, "20190112", 60, "YR", "F", "CA", "EXP"),
            (231, 23, 1, "20190113", 25, "YR", "M", "US", "EXP"),
            (241, 24, 1, "20190114", 30, "YR", "F", "US", "EXP"),
            (251, 25, 1, "20190115", 3, "DEC", "M", "US", "EXP"),
            (261, 26, 1, "20190116", 70, "YR", "F", "US", "EXP"),
        ],
        drug=[
            (101, 10, 1, "PS", "SPRAVATO", "ESKETAMINE"),
            (201, 20, 1, "PS", "SPRAVATO", "ESKETAMINE HYDROCHLORIDE"),
            (201, 20, 2, "C", "ZOLOFT", "SERTRALINE"),         # concomitant: not exposure
            (211, 21, 1, "PS", "ZOLOFT", "SERTRALINE"),
            (221, 22, 1, "SS", "LEXAPRO", "ESCITALOPRAM"),
            (231, 23, 1, "PS", "KETALAR", "KETAMINE HYDROCHLORIDE"),
            (241, 24, 1, "PS", "ASPIRIN", "ASPIRIN"),
            (241, 24, 2, "C", "SPRAVATO", "ESKETAMINE"),       # concomitant: not exposure
            (251, 25, 1, "PS", "KETAMINE", ""),
            (261, 26, 1, "PS", "CELEXA", "CITALOPRAM"),
        ],
        reac=[
            (101, 10, "Nausea", ""),
            (201, 20, "Dissociation", ""), (201, 20, "Nausea", ""),
            (211, 21, "Nausea", ""),
            (221, 22, "Insomnia", ""),
            (231, 23, "Cystitis", ""),
            (241, 24, "Dissociation", ""),
            (251, 25, "Hallucination", ""),
            (261, 26, "Nausea", ""), (261, 26, "NAUSEA", ""),  # same term twice: counted once
        ],
        outc=[(201, 20, "HO"), (231, 23, "OT")],
        indi=[(231, 23, 1, "Anaesthesia"), (251, 25, 1, "Major depression")],
    )
    # Quarter 2: case 10 version 2 (replaces version 1), case 30, deleted case 99
    make_zip(raw / "faers_ascii_2019q2.zip", "19Q2",
        demo=[
            (102, 10, 2, "20190405", 40, "YR", "F", "US", "EXP"),
            (301, 30, 1, "20190406", 45, "YR", "M", "US", "EXP"),
            (991, 99, 1, "20190407", 45, "YR", "M", "US", "EXP"),
        ],
        drug=[
            (102, 10, 1, "PS", "SPRAVATO", "ESKETAMINE"),
            (301, 30, 1, "PS", "ZOLOFT", "SERTRALINE"),
            (301, 30, 2, "SS", "SPRAVATO", "ESKETAMINE"),
            (991, 99, 1, "PS", "SPRAVATO", "ESKETAMINE"),
        ],
        reac=[
            (102, 10, "Dissociation", ""), (102, 10, "Dizziness", ""),
            (301, 30, "Dissociation", ""),
            (991, 99, "Dissociation", ""),
        ],
        outc=[], indi=[], deleted=[99],
    )
    dbp = tmp / "test.sqlite"
    old = sys.argv
    for name, extra in [("02_load_faers", ["--raw", str(raw)]), ("03_deduplicate", []),
                        ("04_signals", ["--out", str(tmp / "signals.csv")])]:
        sys.argv = [name, "--db", str(dbp)] + extra
        load(name).main()
    sys.argv = old
    con = sqlite3.connect(dbp)
    yield con
    con.close()


def test_match_drugs_word_boundaries():
    assert common.match_drugs("ESKETAMINE HYDROCHLORIDE") == {"esketamine"}
    assert common.match_drugs("KETAMINE") == {"ketamine"}
    assert common.match_drugs("ESCITALOPRAM OXALATE") == {"escitalopram"}
    assert common.match_drugs("CITALOPRAM") == {"citalopram"}
    assert common.match_drugs("DESVENLAFAXINE") == {"desvenlafaxine"}
    assert common.match_drugs("VENLAFAXINE HCL") == {"venlafaxine"}
    assert common.match_drugs("OLANZAPINE\\FLUOXETINE") == {"fluoxetine"}
    assert common.match_drugs(None) == set()


def test_ketamine_indication():
    assert common.ketamine_indication("Anaesthesia") == "anaesthesia or sedation"
    assert common.ketamine_indication("Major depression") == "psychiatric"
    assert common.ketamine_indication("Product used for unknown indication") == "unknown"
    assert common.ketamine_indication(None) == "unknown"
    assert common.ketamine_indication("Cancer pain") == "pain"


def test_deduplication(db):
    kept = {r[0] for r in db.execute("SELECT primaryid FROM report")}
    assert 102 in kept and 101 not in kept      # latest version only
    assert 991 not in kept                      # deleted case
    assert len(kept) == 9


def test_exposures(db):
    n = dict(db.execute("SELECT exposure, COUNT(*) FROM exposure_report GROUP BY exposure"))
    assert n["esketamine"] == 3                 # 102, 201, 301 (not 241: concomitant)
    assert n["sertraline"] == 2                 # 211, 301 (not 201: concomitant)
    assert n["ketamine"] == 2
    assert n["ketamine: anaesthesia or sedation"] == 1
    assert n["ketamine: psychiatric"] == 1


def row(db, exposure, background, pt):
    df = pd.read_sql("SELECT * FROM signals WHERE exposure=? AND background=? AND pt=?",
                     db, params=(exposure, background, pt))
    assert len(df) == 1
    return df.iloc[0]


def test_two_by_two_all_faers(db):
    # Esketamine reports: 102, 201, 301. Dissociation on all three, and on 241 (not exposed).
    r = row(db, "esketamine", "All FAERS", "Dissociation")
    assert (r.a, r.b, r.c, r.d) == (3, 0, 1, 5)
    # Nausea: 201 among esketamine; 211 and 261 elsewhere (261 counted once).
    r = row(db, "esketamine", "All FAERS", "Nausea")
    assert (r.a, r.b, r.c, r.d) == (1, 2, 2, 4)
    assert math.isclose(r.prr, (1 / 3) / (2 / 6))
    assert math.isclose(r.ror, (1 * 4) / (2 * 2))


def test_two_by_two_comparators(db):
    # Comparator pool: 211, 221, 261, 301. Report 301 also has esketamine, so
    # it leaves the pool: reference = 211, 221, 261.
    r = row(db, "esketamine", "Other antidepressants", "Nausea")
    assert (r.a, r.b, r.c, r.d) == (1, 2, 2, 1)
    r = row(db, "esketamine", "Other antidepressants", "Dissociation")
    assert (r.a, r.b, r.c, r.d) == (3, 0, 0, 3)


def test_stats_known_values():
    sig = load("04_signals")
    df = pd.DataFrame({"a": [20], "b": [80], "c": [100], "d": [9800]})
    out = sig.stats(df).iloc[0]
    assert math.isclose(out.prr, 0.2 / (100 / 9900))
    assert math.isclose(out.ror, (20 * 9800) / (80 * 100))
    assert out.ror_lo < out.ror < out.ror_hi
    assert out.signal_evans and out.signal_ror and out.signal_ic


def test_validate_and_export_run(db, tmp_path, monkeypatch):
    dbp = db.execute("PRAGMA database_list").fetchone()[2]
    val = load("05_validate")
    sig = pd.read_sql("SELECT * FROM signals", db)
    res = val.check(sig)
    dis = res[res["reaction"] == "Dissociation"].iloc[0]
    assert dis["reports"] == 3 and dis["expected_signal"]
    exp = load("06_export")
    monkeypatch.setattr(exp, "OUTPUTS", tmp_path)
    monkeypatch.setattr(sys, "argv", ["06_export", "--db", dbp])
    exp.main()
    by_q = pd.read_csv(tmp_path / "reports_by_quarter.csv")
    esk = by_q[by_q["exposure"] == "esketamine"].set_index("quarter")["reports"].to_dict()
    assert esk == {"2019Q1": 1, "2019Q2": 2}
    demo = pd.read_csv(tmp_path / "demographics.csv")
    assert demo.loc[demo["exposure"] == "ketamine", "age_band"].tolist().count("30 to 44") == 1


def test_term_category():
    assert common.term_category("Dissociation") == "Clinical"
    assert common.term_category("Device issue") == "Product, device or use"
    assert common.term_category("Intentional overdose") == "Clinical"
    assert common.term_category("Hospitalisation") == "Procedure or administrative"
    assert common.term_category("Drug ineffective") == "Lack of effect"
