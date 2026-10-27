"""Export tidy tables for Power BI to outputs/.

    signals.csv            (written by 04) every drug-reaction pair and its statistics
    validation.csv         (written by 05) positive and negative controls
    drugs.csv              drug lookup: exposure, generic drug, group
    reports_by_quarter.csv reports per exposure and quarter, with serious counts
    demographics.csv       reports per exposure, sex and age band
    outcomes.csv           reports per exposure and outcome code
    data_summary.csv       quarters loaded, report totals, lines skipped
"""

import argparse

import pandas as pd

from common import COMPARATORS, DRUGS, OUTPUTS, connect

OUTCOMES = {"DE": "Death", "LT": "Life-threatening", "HO": "Hospitalization",
            "DS": "Disability", "CA": "Congenital anomaly", "RI": "Required intervention",
            "OT": "Other serious"}
AGE_BANDS = [0, 18, 30, 45, 65, 200]
AGE_LABELS = ["Under 18", "18 to 29", "30 to 44", "45 to 64", "65 and over"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    args = ap.parse_args()
    con = connect(args.db)
    OUTPUTS.mkdir(exist_ok=True)

    exps = pd.read_sql("SELECT DISTINCT exposure FROM exposure_report", con)["exposure"]
    drugs = pd.DataFrame({"exposure": exps})
    drugs["drug"] = drugs["exposure"].str.split(":").str[0]
    drugs["group"] = drugs["drug"].map(lambda d: DRUGS[d][0])
    drugs["is_comparator"] = drugs["drug"].isin(COMPARATORS)
    drugs["is_subgroup"] = drugs["exposure"].str.contains(":")
    drugs.sort_values("exposure").to_csv(OUTPUTS / "drugs.csv", index=False)

    rep = pd.read_sql(
        """SELECT e.exposure, r.primaryid, r.quarter, r.sex, r.age_years,
                  EXISTS (SELECT 1 FROM outc o WHERE o.primaryid = r.primaryid) AS serious
           FROM exposure_report e JOIN report r USING (primaryid)""", con)

    by_q = (rep.groupby(["exposure", "quarter"])
               .agg(reports=("primaryid", "size"), serious=("serious", "sum")).reset_index())
    by_q["year"] = by_q["quarter"].str[:4].astype(int)
    by_q.to_csv(OUTPUTS / "reports_by_quarter.csv", index=False)

    rep["sex"] = rep["sex"].map({"F": "Female", "M": "Male"}).fillna("Not reported")
    rep["age_band"] = pd.cut(rep["age_years"], AGE_BANDS, right=False, labels=AGE_LABELS)
    rep["age_band"] = rep["age_band"].astype(object).fillna("Not reported")
    (rep.groupby(["exposure", "sex", "age_band"]).size().rename("reports").reset_index()
        .to_csv(OUTPUTS / "demographics.csv", index=False))

    outc = pd.read_sql(
        """SELECT e.exposure, o.outc_cod, COUNT(*) AS reports
           FROM exposure_report e JOIN outc o USING (primaryid)
           GROUP BY e.exposure, o.outc_cod""", con)
    outc["outcome"] = outc["outc_cod"].map(OUTCOMES).fillna(outc["outc_cod"])
    outc.to_csv(OUTPUTS / "outcomes.csv", index=False)

    loaded = pd.read_sql("SELECT quarter, reports AS report_versions, skipped_lines FROM loaded ORDER BY quarter", con)
    kept = pd.read_sql("SELECT quarter, COUNT(*) AS cases_kept FROM report GROUP BY quarter", con)
    loaded.merge(kept, on="quarter", how="left").to_csv(OUTPUTS / "data_summary.csv", index=False)
    con.close()
    print(f"Exported tables to {OUTPUTS}")


if __name__ == "__main__":
    main()
