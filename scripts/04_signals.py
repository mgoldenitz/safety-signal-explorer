"""Disproportionality statistics for every exposure and reaction term.

For each exposure X and reaction R, with report counts:
    a = X with R          b = X without R
    c = others with R     d = others without R

"Others" is one of two backgrounds:
    All FAERS               every other de-duplicated report
    Other antidepressants   reports naming one of the 12 comparators, minus
                            reports that also name X (study drugs only)

Measures:
    PRR with 95% CI, chi-squared with Yates correction
    Evans signal: a >= 3, PRR >= 2, chi-squared >= 4
    ROR with 95% CI; ROR signal: a >= 3 and lower bound > 1
    IC (information component) with the IC025 approximation from Noren et
    al.; IC signal: IC025 > 0

Writes the signals table to the database and outputs/signals.csv.
"""

import argparse

import pandas as pd

from common import COMPARATORS, OUTPUTS, REPO, connect, stats, term_category


def run_counts_sql(con):
    sql = (REPO / "sql" / "04_signal_counts.sql").read_text()
    names = ", ".join(f"'{d}'" for d in COMPARATORS)
    con.executescript(sql.replace(":comparators", names))


def build(con):
    run_counts_sql(con)
    q = lambda s: pd.read_sql(s, con)
    total = con.execute("SELECT COUNT(*) FROM report").fetchone()[0]
    n_comp = con.execute("SELECT COUNT(*) FROM comparator_report").fetchone()[0]

    a = q("SELECT exposure, pt_id, a FROM n_exposure_pt")
    nx = q("SELECT exposure, n AS n_x FROM n_exposure")
    pt_all = q("SELECT pt_id, n AS n_pt FROM n_pt_all")
    pt_comp = q("SELECT pt_id, n AS n_pt_comp FROM n_pt_comparator")
    ov_pt = q("SELECT exposure, pt_id, n AS ov_pt FROM n_overlap_pt")
    ov = q("SELECT exposure, n AS ov FROM n_overlap")
    terms = q("SELECT pt_id, pt FROM pt")

    base = a.merge(nx, on="exposure")

    # Background 1: all of FAERS
    full = base.merge(pt_all, on="pt_id")
    full["b"] = full["n_x"] - full["a"]
    full["c"] = full["n_pt"] - full["a"]
    full["d"] = total - full["n_x"] - full["c"]
    full["background"] = "All FAERS"

    # Background 2: comparator antidepressants (study drugs only)
    study = base[~base["exposure"].isin(COMPARATORS)]
    comp = (study.merge(pt_comp, on="pt_id", how="left")
                 .merge(ov_pt, on=["exposure", "pt_id"], how="left")
                 .merge(ov, on="exposure", how="left")
                 .fillna({"n_pt_comp": 0, "ov_pt": 0, "ov": 0}))
    comp["b"] = comp["n_x"] - comp["a"]
    comp["c"] = comp["n_pt_comp"] - comp["ov_pt"]
    comp["d"] = (n_comp - comp["ov"]) - comp["c"]
    comp["background"] = "Other antidepressants"

    cols = ["exposure", "background", "pt_id", "a", "b", "c", "d"]
    sig = stats(pd.concat([full[cols], comp[cols]], ignore_index=True))
    sig = sig.merge(terms, on="pt_id")
    sig["term_category"] = sig["pt"].map(term_category)
    for k in "abcd":
        sig[k] = sig[k].astype(int)
    order = ["exposure", "background", "pt", "term_category", "a", "b", "c", "d", "expected", "prr", "prr_lo",
             "prr_hi", "chi2", "ror", "ror_lo", "ror_hi", "ic", "ic025",
             "signal_evans", "signal_ror", "signal_ic"]
    return sig[order].sort_values(["exposure", "background", "a"], ascending=[True, True, False])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--out", default=str(OUTPUTS / "signals.csv"))
    args = ap.parse_args()
    con = connect(args.db)
    sig = build(con)
    sig.to_sql("signals", con, if_exists="replace", index=False)
    con.close()
    sig.to_csv(args.out, index=False)
    flagged = sig[sig["signal_ror"]].groupby(["exposure", "background", "term_category"]).size().unstack(fill_value=0)
    print(f"{len(sig):,} drug-reaction pairs written to {args.out}")
    print("Pairs flagged by ROR (a >= 3, lower 95% bound > 1):")
    print(flagged.to_string())


if __name__ == "__main__":
    main()
