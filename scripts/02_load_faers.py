"""Load FAERS quarterly files into SQLite.

Reads every faers_ascii_*.zip in $SSX_DATA/raw/faers and keeps:
  demo      every report (one row per primaryid) with case id, version, date, age, sex
  pt, reac  every reaction on every report (reaction terms stored once in pt)
  exposure  suspect drug rows that match one of the 14 study or comparator drugs
  indi      indications for ketamine drug rows (used to split ketamine reports)
  outc      outcome codes for reports that have a matched drug
  deleted   case ids the FDA has withdrawn

All reactions are kept because the full-database comparison needs reaction
counts across every report. Other drugs are not kept, since only the 14
matched drugs are compared.

Each quarter is loaded once; re-running skips loaded quarters. Use --rebuild
to start again.
"""

import argparse
import csv
import io
import re
import zipfile

import numpy as np
import pandas as pd

from common import RAW_FAERS, SUSPECT_ROLES, connect, match_drugs

SCHEMA = """
CREATE TABLE IF NOT EXISTS loaded (quarter TEXT PRIMARY KEY, reports INTEGER, skipped_lines INTEGER);
CREATE TABLE IF NOT EXISTS demo (
    primaryid INTEGER PRIMARY KEY, caseid INTEGER, caseversion INTEGER,
    fda_dt TEXT, quarter TEXT, sex TEXT, age_years REAL, occr_country TEXT, rept_cod TEXT);
CREATE TABLE IF NOT EXISTS pt (pt_id INTEGER PRIMARY KEY, pt_key TEXT UNIQUE, pt TEXT);
CREATE TABLE IF NOT EXISTS reac (primaryid INTEGER, pt_id INTEGER, PRIMARY KEY (primaryid, pt_id)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS exposure (
    primaryid INTEGER, drug_seq INTEGER, drug TEXT, role_cod TEXT, drugname TEXT, prod_ai TEXT);
CREATE TABLE IF NOT EXISTS indi (primaryid INTEGER, drug_seq INTEGER, indi_pt TEXT);
CREATE TABLE IF NOT EXISTS outc (primaryid INTEGER, outc_cod TEXT, PRIMARY KEY (primaryid, outc_cod)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS deleted (caseid INTEGER PRIMARY KEY);
"""

AGE_FACTOR = {"YR": 1, "DEC": 10, "MON": 1 / 12, "WK": 1 / 52, "DY": 1 / 365, "HR": 1 / 8760}


class Counter:
    def __init__(self):
        self.n = 0


def member(zf, prefix):
    """Find the ASCII file for a table (DEMO, DRUG, ...) whatever its case or folder."""
    pat = re.compile(rf"(^|/){prefix}\d\dQ\d\.txt$", re.I)
    hits = [n for n in zf.namelist() if pat.search(n)]
    return hits[0] if hits else None


def read_table(zf, prefix, usecols, bad):
    name = member(zf, prefix)
    if name is None:
        raise FileNotFoundError(f"{prefix} file not found in {zf.filename}")
    raw = zf.read(name).decode("latin-1")
    lines = raw.count("\n") - (0 if raw.endswith("\n") else -1)
    df = pd.read_csv(io.StringIO(raw), sep="$", dtype=str, quoting=csv.QUOTE_NONE,
                     on_bad_lines="skip", index_col=False)
    bad.n += max(lines - 1 - len(df), 0)
    df.columns = [c.strip().lower() for c in df.columns]
    # Older files use gndr_cod and outc_code.
    df = df.rename(columns={"gndr_cod": "sex", "outc_code": "outc_cod"})
    for c in usecols:
        if c not in df.columns:
            df[c] = None
    return df[usecols]


def read_deleted(zf):
    ids = []
    for n in zf.namelist():
        if re.search(r"delete", n, re.I) and n.lower().endswith(".txt"):
            with zf.open(n) as fh:
                for line in io.TextIOWrapper(fh, encoding="latin-1"):
                    line = line.strip().split("$")[0]
                    if line.isdigit():
                        ids.append(int(line))
    return ids


def to_int(s):
    return pd.to_numeric(s, errors="coerce").astype("Int64")


def load_quarter(con, path, quarter):
    bad = Counter()
    with zipfile.ZipFile(path) as zf:
        demo = read_table(zf, "DEMO", ["primaryid", "caseid", "caseversion", "fda_dt", "sex",
                                       "age", "age_cod", "occr_country", "rept_cod"], bad)
        drug = read_table(zf, "DRUG", ["primaryid", "drug_seq", "role_cod", "drugname", "prod_ai"], bad)
        reac = read_table(zf, "REAC", ["primaryid", "pt"], bad)
        outc = read_table(zf, "OUTC", ["primaryid", "outc_cod"], bad)
        indi = read_table(zf, "INDI", ["primaryid", "indi_drug_seq", "indi_pt"], bad)
        deleted = read_deleted(zf)

    # Reports
    demo["primaryid"] = to_int(demo["primaryid"])
    demo = demo.dropna(subset=["primaryid"]).drop_duplicates("primaryid")
    age = pd.to_numeric(demo["age"], errors="coerce")
    factor = demo["age_cod"].str.strip().str.upper().map(AGE_FACTOR)
    demo["age_years"] = (age * factor).where(lambda a: (a >= 0) & (a <= 120))
    demo["caseid"] = to_int(demo["caseid"])
    demo["caseversion"] = to_int(demo["caseversion"]).fillna(1)
    demo["quarter"] = quarter
    demo["sex"] = demo["sex"].str.strip().str.upper()
    demo = demo[["primaryid", "caseid", "caseversion", "fda_dt", "quarter", "sex",
                 "age_years", "occr_country", "rept_cod"]]
    con.executemany("INSERT OR REPLACE INTO demo VALUES (?,?,?,?,?,?,?,?,?)",
                    demo.astype(object).where(demo.notna(), None).itertuples(index=False))

    # Reaction terms: one id per term, matched without regard to case
    reac["primaryid"] = to_int(reac["primaryid"])
    reac["pt"] = reac["pt"].str.strip()
    reac = reac.dropna()
    reac = reac[reac["pt"] != ""]
    reac["pt_key"] = reac["pt"].str.upper()
    terms = reac.drop_duplicates("pt_key")[["pt_key", "pt"]]
    con.executemany("INSERT OR IGNORE INTO pt (pt_key, pt) VALUES (?, ?)", terms.itertuples(index=False))
    ids = dict(con.execute("SELECT pt_key, pt_id FROM pt"))
    reac["pt_id"] = reac["pt_key"].map(ids)
    con.executemany("INSERT OR IGNORE INTO reac VALUES (?, ?)",
                    reac[["primaryid", "pt_id"]].astype(int).itertuples(index=False))

    # Suspect drug rows that match a study or comparator drug
    drug["role_cod"] = drug["role_cod"].str.strip().str.upper()
    drug = drug[drug["role_cod"].isin(SUSPECT_ROLES)].copy()
    text = drug["prod_ai"].fillna("") + " | " + drug["drugname"].fillna("")
    drug["drugs"] = text.map(match_drugs)
    drug = drug[drug["drugs"].map(len) > 0].explode("drugs").rename(columns={"drugs": "drug"})
    drug["primaryid"] = to_int(drug["primaryid"])
    drug["drug_seq"] = to_int(drug["drug_seq"])
    exp = drug[["primaryid", "drug_seq", "drug", "role_cod", "drugname", "prod_ai"]]
    con.executemany("INSERT INTO exposure VALUES (?,?,?,?,?,?)",
                    exp.astype(object).where(exp.notna(), None).itertuples(index=False))

    matched = set(exp["primaryid"].dropna().astype(int))

    # Indications for ketamine rows
    ket = exp[exp["drug"] == "ketamine"][["primaryid", "drug_seq"]].dropna().astype(int)
    indi["primaryid"] = to_int(indi["primaryid"])
    indi["drug_seq"] = to_int(indi["indi_drug_seq"])
    indi = indi.dropna(subset=["primaryid", "drug_seq"])
    indi = indi.astype({"primaryid": int, "drug_seq": int}).merge(ket, on=["primaryid", "drug_seq"])
    con.executemany("INSERT INTO indi VALUES (?,?,?)",
                    indi[["primaryid", "drug_seq", "indi_pt"]].itertuples(index=False))

    # Outcomes for matched reports
    outc["primaryid"] = to_int(outc["primaryid"])
    outc = outc.dropna()
    outc = outc[outc["primaryid"].astype(int).isin(matched)]
    outc["outc_cod"] = outc["outc_cod"].str.strip().str.upper()
    con.executemany("INSERT OR IGNORE INTO outc VALUES (?, ?)",
                    outc.astype({"primaryid": int}).itertuples(index=False))

    con.executemany("INSERT OR IGNORE INTO deleted VALUES (?)", [(i,) for i in deleted])
    con.execute("INSERT INTO loaded VALUES (?, ?, ?)", (quarter, len(demo), bad.n))
    con.commit()
    return len(demo), len(exp), bad.n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="delete the database and load again")
    ap.add_argument("--raw", default=str(RAW_FAERS))
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    con = connect(args.db)
    if args.rebuild:
        for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            con.execute(f"DROP TABLE {t}")
    con.executescript(SCHEMA)
    done = {q for (q,) in con.execute("SELECT quarter FROM loaded")}

    from pathlib import Path
    zips = sorted(Path(args.raw).glob("faers_ascii_*.zip"))
    if not zips:
        raise SystemExit(f"No FAERS zip files in {args.raw}. Run 01_download_faers.py first.")
    for z in zips:
        m = re.search(r"(\d{4})q(\d)", z.name, re.I)
        quarter = f"{m.group(1)}Q{m.group(2)}"
        if quarter in done:
            print(f"{quarter}: already loaded")
            continue
        n, e, b = load_quarter(con, z, quarter)
        print(f"{quarter}: {n:,} reports, {e:,} matched drug rows, {b} unreadable lines skipped")

    con.execute("CREATE INDEX IF NOT EXISTS ix_demo_case ON demo (caseid)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_exposure ON exposure (primaryid)")
    con.commit()
    con.close()


if __name__ == "__main__":
    main()
