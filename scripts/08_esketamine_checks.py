"""Two checks on the esketamine reports.

1. Route. Spravato is a nasal spray, but "esketamine" in FAERS can also be
   esketamine given by injection (sold as Ketanest in parts of Europe). Each
   esketamine report is put in one group from its esketamine drug rows:
     Spravato or nasal   drug name says Spravato, or the route or dose form says nasal
     Other route         generic name only, and a non-nasal route (intravenous, oral, ...)
     Route not given     generic name only, and no route
   The signals are then recomputed for the "Spravato or nasal" group alone.

2. The 2025 Q2 jump. Esketamine reports rose from about 1,000 a quarter to
   2,444 in 2025 Q2. For each quarter this counts reports by sender
   (manufacturer), reporter occupation, report type, country and the quarter
   the case was first received, so a burst from one source shows up. The
   signals are also recomputed with 2025 Q2 left out.

The loaded database does not keep route, sender or occupation, so this script
reads those fields again from the raw quarterly zips, only for the esketamine
reports. Needs 02 to 04 to have been run.

Writes to outputs/:
  esketamine_route_summary.csv    reports per route group, by year
  esketamine_subgroup_signals.csv every reaction with 3+ reports, full vs subgroups
  esketamine_reporters.csv        reports per quarter by sender, occupation, type, country, first quarter
  esketamine_2025q2_terms.csv     reaction counts in 2025 Q2 against the 2024 quarterly average
"""

import argparse
import importlib.util
import re
import zipfile
from pathlib import Path

import pandas as pd

from common import OUTPUTS, RAW_FAERS, REPO, SUSPECT_ROLES, connect, match_drugs, stats

SPIKE = "2025Q2"
NON_NASAL = ["INTRAVENOUS", "INTRAMUSCULAR", "SUBCUTANEOUS", "ORAL", "SUBLINGUAL",
             "EPIDURAL", "INTRATHECAL", "RECTAL", "TRANSDERMAL", "BUCCAL", "INHALATION"]


def name_group(drugnames):
    return "Spravato" if any("SPRAVATO" in str(n).upper() for n in drugnames) else "generic"


def route_group(rows):
    """rows: esketamine drug rows for one report, with drugname, route, dose_form, dose_vbm."""
    if name_group(rows["drugname"]) == "Spravato":
        return "Spravato or nasal"
    text = " ".join(rows[["route", "dose_form", "dose_vbm"]].fillna("").astype(str).agg(" ".join, axis=1)).upper()
    if "NASAL" in text or "SPRAY" in text:
        return "Spravato or nasal"
    route = " ".join(rows["route"].fillna("").astype(str)).upper()
    if any(k in route for k in NON_NASAL):
        return "Other route"
    return "Route not given"


def quarter_of(date):
    s = str(date or "")
    if not re.fullmatch(r"\d{8}", s):
        return None
    return f"{s[:4]}Q{(int(s[4:6]) - 1) // 3 + 1}"


def read_raw(raw_dir, wanted):
    """wanted: {quarter: set(primaryid)}. Returns esketamine drug rows and demo rows."""
    loader = load_module("02_load_faers")
    drugs, demos = [], []
    for z in sorted(Path(raw_dir).glob("faers_ascii_*.zip")):
        m = re.search(r"(\d{4})q(\d)", z.name, re.I)
        quarter = f"{m.group(1)}Q{m.group(2)}"
        ids = wanted.get(quarter)
        if not ids:
            continue
        bad = loader.Counter()
        with zipfile.ZipFile(z) as zf:
            drug = loader.read_table(zf, "DRUG", ["primaryid", "drug_seq", "role_cod", "drugname", "prod_ai",
                                                  "route", "dose_form", "dose_vbm"], bad)
            demo = loader.read_table(zf, "DEMO", ["primaryid", "mfr_sndr", "occp_cod", "rept_cod",
                                                  "occr_country", "init_fda_dt", "caseversion", "lit_ref"], bad)
        for df in (drug, demo):
            df["primaryid"] = pd.to_numeric(df["primaryid"], errors="coerce")
        drug = drug[drug["primaryid"].isin(ids)].copy()
        drug["role_cod"] = drug["role_cod"].str.strip().str.upper()
        drug = drug[drug["role_cod"].isin(SUSPECT_ROLES)]
        text = drug["prod_ai"].fillna("") + " | " + drug["drugname"].fillna("")
        drug = drug[text.map(lambda t: "esketamine" in match_drugs(t))]
        demo = demo[demo["primaryid"].isin(ids)].drop_duplicates("primaryid").copy()
        drug["quarter"] = demo["quarter"] = quarter
        drugs.append(drug)
        demos.append(demo)
        print(f"{quarter}: {len(demo):,} esketamine reports read")
    return pd.concat(drugs, ignore_index=True), pd.concat(demos, ignore_index=True)


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def subgroup_signals(con, ids, label):
    """ROR, PRR and IC for a subset of esketamine reports against every report
    with no esketamine. Other esketamine reports are left out of both sides."""
    con.execute("DROP TABLE IF EXISTS temp.sub")
    con.execute("CREATE TEMP TABLE sub (primaryid INTEGER PRIMARY KEY)")
    con.executemany("INSERT INTO temp.sub VALUES (?)", [(int(i),) for i in ids])
    total = con.execute("SELECT COUNT(*) FROM report").fetchone()[0]
    n_esk = con.execute("SELECT n FROM n_exposure WHERE exposure = 'esketamine'").fetchone()[0]
    a = pd.read_sql("SELECT x.pt_id, COUNT(*) AS a FROM reac x JOIN temp.sub USING (primaryid) GROUP BY x.pt_id", con)
    pt_all = pd.read_sql("SELECT pt_id, n AS n_pt FROM n_pt_all", con)
    pt_esk = pd.read_sql("SELECT pt_id, a AS n_pt_esk FROM n_exposure_pt WHERE exposure = 'esketamine'", con)
    df = a.merge(pt_all, on="pt_id").merge(pt_esk, on="pt_id", how="left").fillna({"n_pt_esk": 0})
    n_sub = len(ids)
    df["b"] = n_sub - df["a"]
    df["c"] = df["n_pt"] - df["n_pt_esk"]
    df["d"] = (total - n_esk) - df["c"]
    out = stats(df[["pt_id", "a", "b", "c", "d"]])
    out["subgroup"] = label
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--raw", default=str(RAW_FAERS))
    ap.add_argument("--out", default=str(OUTPUTS))
    args = ap.parse_args()
    out = Path(args.out)
    con = connect(args.db)

    rep = pd.read_sql("""SELECT r.primaryid, r.quarter FROM report r
                         JOIN exposure_report e USING (primaryid) WHERE e.exposure = 'esketamine'""", con)
    wanted = rep.groupby("quarter")["primaryid"].apply(set).to_dict()
    print(f"{len(rep):,} de-duplicated esketamine reports")
    drug, demo = read_raw(args.raw, wanted)

    # Check 1: route
    groups = pd.DataFrame([(pid, route_group(rows)) for pid, rows in drug.groupby("primaryid")],
                          columns=["primaryid", "route_group"])
    rep = rep.merge(groups, on="primaryid", how="left").fillna({"route_group": "Route not given"})
    rep["year"] = rep["quarter"].str[:4]
    summary = rep.pivot_table(index="year", columns="route_group", values="primaryid",
                              aggfunc="count", fill_value=0)
    summary.loc["All years"] = summary.sum()
    summary.to_csv(out / "esketamine_route_summary.csv")
    print("\nCheck 1. Esketamine reports by route group")
    print(summary.to_string())
    routes = drug["route"].fillna("(blank)").str.strip().str.upper().value_counts().head(10)
    print("\nMost common route values on esketamine drug rows")
    print(routes.to_string())

    # Check 2: who sent the reports
    demo = demo.merge(rep[["primaryid"]], on="primaryid")
    demo["first_quarter"] = demo["init_fda_dt"].map(quarter_of)
    demo["mfr_sndr"] = demo["mfr_sndr"].fillna("(blank)").str.strip().str.upper()
    demo["has_lit_ref"] = demo["lit_ref"].fillna("").str.strip() != ""
    long = []
    for field in ["mfr_sndr", "occp_cod", "rept_cod", "occr_country", "first_quarter", "has_lit_ref"]:
        t = demo.assign(value=demo[field].fillna("(blank)").astype(str)).groupby(["quarter", "value"]).size()
        long.append(t.rename("reports").reset_index().assign(field=field))
    long = pd.concat(long)[["field", "quarter", "value", "reports"]]
    long.to_csv(out / "esketamine_reporters.csv", index=False)

    print("\nCheck 2. Esketamine reports per quarter, top sender's share and reports first received that quarter")
    per_q = demo.groupby("quarter").agg(
        reports=("primaryid", "size"),
        top_sender=("mfr_sndr", lambda s: s.value_counts().index[0]),
        top_sender_share=("mfr_sndr", lambda s: s.value_counts(normalize=True).iloc[0]),
    )
    per_q["first_received_same_quarter"] = demo.assign(same=demo["first_quarter"] == demo["quarter"]) \
        .groupby("quarter")["same"].mean()
    print(per_q.to_string(float_format=lambda x: f"{x:.2f}"))

    spike = demo[demo["quarter"] == SPIKE]
    if len(spike):
        for field in ["mfr_sndr", "occp_cod", "rept_cod", "occr_country", "first_quarter", "has_lit_ref"]:
            print(f"\n{SPIKE} by {field}")
            print(spike[field].fillna("(blank)").astype(str).value_counts().head(8).to_string())

        # Reaction terms behind the jump
        terms = pd.read_sql("SELECT pt_id, pt FROM pt", con)
        ids_q = rep[["primaryid", "quarter"]]
        con.execute("DROP TABLE IF EXISTS temp.eskq")
        con.execute("CREATE TEMP TABLE eskq (primaryid INTEGER PRIMARY KEY, quarter TEXT)")
        con.executemany("INSERT INTO temp.eskq VALUES (?, ?)", ids_q.itertuples(index=False))
        pq = pd.read_sql("""SELECT q.quarter, x.pt_id, COUNT(*) AS n FROM temp.eskq q
                            JOIN reac x USING (primaryid) WHERE q.quarter LIKE '2024Q%' OR q.quarter = ?
                            GROUP BY q.quarter, x.pt_id""", con, params=(SPIKE,))
        t = (pq.assign(period=pq["quarter"].where(pq["quarter"] == SPIKE, "2024"))
               .groupby(["period", "pt_id"])["n"].sum().unstack("period", fill_value=0))
        t["2024_per_quarter"] = t.get("2024", 0) / 4
        t = t.rename(columns={SPIKE: f"{SPIKE}_reports"}).drop(columns="2024", errors="ignore")
        t["increase"] = t[f"{SPIKE}_reports"] - t["2024_per_quarter"]
        t = t.merge(terms, left_index=True, right_on="pt_id").sort_values("increase", ascending=False)
        t = t[["pt", f"{SPIKE}_reports", "2024_per_quarter", "increase"]]
        t.to_csv(out / "esketamine_2025q2_terms.csv", index=False)
        print(f"\nReaction terms with the largest rise in {SPIKE} over the 2024 quarterly average")
        print(t.head(15).to_string(index=False, float_format=lambda x: f"{x:.0f}"))

    # Signals: full set against the two subsets
    full = pd.read_sql("""SELECT pt, a, ror, ror_lo, ror_hi, signal_ror FROM signals
                          WHERE exposure = 'esketamine' AND background = 'All FAERS' AND a >= 3""", con)
    terms = pd.read_sql("SELECT pt_id, pt FROM pt", con)
    subsets = {
        "nasal": rep.loc[rep["route_group"] == "Spravato or nasal", "primaryid"],
        "no_2025q2": rep.loc[rep["quarter"] != SPIKE, "primaryid"],
    }
    res = full.rename(columns={c: f"all_{c}" for c in full.columns if c != "pt"})
    for label, ids in subsets.items():
        s = subgroup_signals(con, ids, label).merge(terms, on="pt_id")
        s = s[["pt", "a", "ror", "ror_lo", "ror_hi", "signal_ror"]]
        res = res.merge(s.rename(columns={c: f"{label}_{c}" for c in s.columns if c != "pt"}), on="pt", how="left")
    res = res.sort_values("all_a", ascending=False)
    res.to_csv(out / "esketamine_subgroup_signals.csv", index=False)

    flagged = res[res["all_signal_ror"] == 1]
    print(f"\nSignals: {len(flagged)} reaction terms flagged by ROR for all esketamine reports")
    for label in subsets:
        kept = (flagged[f"{label}_signal_ror"] == 1).sum()
        new = ((res["all_signal_ror"] != 1) & (res[f"{label}_signal_ror"] == 1)).sum()
        print(f"  {label}: {kept} of them still flagged, {new} terms flagged only in this subset")

    val = load_module("05_validate")
    print("\nControls, ROR (lower bound): all reports | Spravato or nasal | without 2025 Q2")
    keyed = res.assign(key=res["pt"].str.upper())
    for exposure, names, expected, _ in val.CONTROLS:
        if exposure != "esketamine":
            continue
        hit = keyed[keyed["key"].isin([n.upper() for n in names])].head(1)
        if hit.empty:
            print(f"  {' / '.join(names)}: fewer than 3 reports")
            continue
        h = hit.iloc[0]
        cell = lambda p: f"{h[p + '_ror']:.2f} ({h[p + '_ror_lo']:.2f})" if pd.notna(h[p + "_ror"]) else "n/a"
        tag = "expected" if expected else "negative control"
        print(f"  {h['pt']} [{tag}]: {cell('all')} | {cell('nasal')} | {cell('no_2025q2')}")
    con.close()


if __name__ == "__main__":
    main()
