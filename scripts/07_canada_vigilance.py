"""Canada Vigilance: load the Health Canada extract and compute the same signals.

Put the unzipped extract in $SSX_DATA/raw/canada_vigilance (any folder depth).
The extract is a set of $-delimited text files with values in double quotes
(layout from Health Canada's "Canada Vigilance Adverse Reaction Online
Database - Data Structure" page). This script uses five of them:

    Reports.txt                    one row per report
    Report_Drug.txt                drugs on each report and their role
    Drug_Product_Ingredients.txt   active ingredients of each drug product
    Reactions.txt                  MedDRA reaction terms and organ classes
    Report_Drug_Indication.txt     indications (used to split ketamine)
    Report_Links_LX.txt            links between reports, including duplicates

Reports initially received from 2019 onward are kept, to match the FAERS
period. When two reports in the extract are linked as duplicates, the earlier one
(lower REPORT_ID) is kept. Drugs count only when their role is "Suspect".

Writes cv_* tables to the database and these files to outputs/:
    cv_signals.csv              same columns as signals.csv
    cv_reports_by_year.csv      reports per exposure and year
    pt_soc.csv                  each reaction term's MedDRA organ class, taken
                                from Canada Vigilance (FAERS has none)
"""

import argparse
import csv
import io
from pathlib import Path

import pandas as pd

from common import (COMPARATORS, DATA, OUTPUTS, connect, ketamine_indication, match_drugs,
                    stats, term_category)

RAW_CV = DATA / "raw" / "canada_vigilance"
START_DATE = "2019-01-01"

COLUMNS = {
    "reports": ["REPORT_ID", "REPORT_NO", "VERSION_NO", "DATRECEIVED", "DATINTRECEIVED", "MAH_NO",
                "REPORT_TYPE_CODE", "REPORT_TYPE_ENG", "REPORT_TYPE_FR", "GENDER_CODE", "GENDER_ENG",
                "GENDER_FR", "AGE", "AGE_Y", "AGE_UNIT_ENG", "AGE_UNIT_FR", "OUTCOME_CODE",
                "OUTCOME_ENG", "OUTCOME_FR", "WEIGHT", "WEIGHT_UNIT_ENG", "WEIGHT_UNIT_FR", "HEIGHT",
                "HEIGHT_UNIT_ENG", "HEIGHT_UNIT_FR", "SERIOUSNESS_CODE", "SERIOUSNESS_ENG",
                "SERIOUSNESS_FR", "DEATH", "DISABILITY", "CONGENITAL_ANOMALY", "LIFE_THREATENING",
                "HOSP_REQUIRED", "OTHER_MEDICALLY_IMP_COND", "REPORTER_TYPE_ENG", "REPORTER_TYPE_FR",
                "SOURCE_CODE", "SOURCE_ENG", "SOURCE_FR", "E2B_IMP_SAFETYREPORT_ID",
                "AUTHORITY_NUMB", "COMPANY_NUMB"],
    "report_drug": ["REPORT_DRUG_ID", "REPORT_ID", "DRUG_PRODUCT_ID", "DRUGNAME", "DRUGINVOLV_ENG",
                    "DRUGINVOLV_FR", "ROUTEADMIN_ENG", "ROUTEADMIN_FR", "UNIT_DOSE_QTY",
                    "DOSE_UNIT_ENG", "DOSE_UNIT_FR", "FREQUENCY", "FREQ_TIME", "FREQUENCY_TIME_ENG",
                    "FREQUENCY_TIME_FR", "FREQ_TIME_UNIT_ENG", "FREQ_TIME_UNIT_FR",
                    "THERAPY_DURATION", "THERAPY_DURATION_UNIT_ENG", "THERAPY_DURATION_UNIT_FR",
                    "DOSAGEFORM_ENG", "DOSAGEFORM_FR"],
    "drug_product_ingredients": ["DRUG_PRODUCT_INGREDIENT_ID", "DRUG_PRODUCT_ID", "DRUGNAME",
                                 "ACTIVE_INGREDIENT_ID", "ACTIVE_INGREDIENT_NAME"],
    "reactions": ["REACTION_ID", "REPORT_ID", "DURATION", "DURATION_UNIT_ENG", "DURATION_UNIT_FR",
                  "PT_NAME_ENG", "PT_NAME_FR", "SOC_NAME_ENG", "SOC_NAME_FR", "MEDDRA_VERSION"],
    "report_drug_indication": ["REPORT_DRUG_ID", "REPORT_ID", "DRUG_PRODUCT_ID", "DRUGNAME",
                               "INDICATION_NAME_ENG", "INDICATION_NAME_FR"],
    "report_links_lx": ["REPORT_LINK_ID", "REPORT_ID", "RECORD_TYPE_ENG", "RECORD_TYPE_FR",
                        "REPORT_LINK_NO"],
}


# File names in the extract differ slightly from the Data Structure page
# (the 2026-06-30 extract has report_links.txt and drug_products.txt).
ALIASES = {"report_links_lx": ["report_links_lx", "report_links"]}


def find_file(raw, name):
    names = ALIASES.get(name, [name])
    hits = [p for p in Path(raw).rglob("*") if p.is_file() and p.stem.lower() in names]
    if not hits:
        raise FileNotFoundError(f"{name}.txt not found under {raw}")
    return hits[0]


def read_cv(raw, name, usecols):
    """Read one extract file. Works with or without a header row."""
    path = find_file(raw, name)
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    cols = COLUMNS[name]
    first = text.split("\n", 1)[0].split("$")[0].strip().strip('"').upper()
    header = 0 if first == cols[0] else None
    df = pd.read_csv(io.StringIO(text), sep="$", quotechar='"', dtype=str, header=header,
                     names=None if header == 0 else cols, index_col=False,
                     on_bad_lines="skip", quoting=csv.QUOTE_MINIMAL)
    df.columns = [str(c).strip().upper() for c in df.columns]
    for c in usecols:
        if c not in df.columns:
            df[c] = None
    return df[usecols].apply(lambda s: s.str.strip())


def parse_date(s):
    """Dates look like 05-JUN-73. Two-digit years above the current year are 1900s."""
    d = pd.to_datetime(s, format="%d-%b-%y", errors="coerce")
    other = d.isna() & s.notna()
    d[other] = pd.to_datetime(s[other], errors="coerce", format="mixed")
    future = d.dt.year > pd.Timestamp.today().year
    d[future] = d[future] - pd.DateOffset(years=100)
    return d


def load(raw):
    rep = read_cv(raw, "reports", ["REPORT_ID", "REPORT_NO", "VERSION_NO", "DATRECEIVED", "DATINTRECEIVED",
                                   "GENDER_ENG", "AGE_Y", "SERIOUSNESS_ENG", "DEATH"])
    rep["received"] = parse_date(rep["DATINTRECEIVED"].fillna(rep["DATRECEIVED"]))
    parsed = rep["received"].notna().mean()
    print(f"Reports: {len(rep):,} rows, received date parsed for {parsed:.1%}")
    rep = rep[rep["received"] >= START_DATE].copy()
    # Keep the latest version if a report number appears more than once.
    rep = (rep.assign(v=pd.to_numeric(rep["VERSION_NO"], errors="coerce"))
              .sort_values("v").drop_duplicates("REPORT_NO", keep="last").drop(columns="v"))

    links = read_cv(raw, "report_links_lx", ["REPORT_ID", "RECORD_TYPE_ENG", "REPORT_LINK_NO"])
    dup = links[links["RECORD_TYPE_ENG"].str.upper().str.startswith("DUPLICATE", na=False)]
    by_no = dict(zip(rep["REPORT_NO"], rep["REPORT_ID"]))
    present = set(rep["REPORT_ID"])
    # For each duplicate pair with both reports in the extract, keep the
    # earlier report (lower REPORT_ID) and drop the other.
    dup_ids = set()
    for rid, link_no in zip(dup["REPORT_ID"], dup["REPORT_LINK_NO"]):
        other = by_no.get(link_no)
        if rid in present and other is not None and other != rid:
            dup_ids.add(max(rid, other, key=int))
    rep = rep[~rep["REPORT_ID"].isin(dup_ids)]
    print(f"Reports received from {START_DATE[:4]}: {len(rep):,} after dropping {len(dup_ids):,} duplicates")
    ids = set(rep["REPORT_ID"])

    rd = read_cv(raw, "report_drug", ["REPORT_DRUG_ID", "REPORT_ID", "DRUG_PRODUCT_ID",
                                      "DRUGNAME", "DRUGINVOLV_ENG"])
    rd = rd[rd["REPORT_ID"].isin(ids) & rd["DRUGINVOLV_ENG"].str.upper().str.startswith("SUSPECT", na=False)]
    ing = read_cv(raw, "drug_product_ingredients", ["DRUG_PRODUCT_ID", "ACTIVE_INGREDIENT_NAME"])
    ing = (ing.dropna().groupby("DRUG_PRODUCT_ID")["ACTIVE_INGREDIENT_NAME"]
              .agg(" | ".join).rename("INGREDIENTS").reset_index())
    rd = rd.merge(ing, on="DRUG_PRODUCT_ID", how="left")
    rd["drug"] = (rd["INGREDIENTS"].fillna("") + " | " + rd["DRUGNAME"].fillna("")).map(match_drugs)
    rd = rd[rd["drug"].map(len) > 0].explode("drug")

    expo = rd[["REPORT_ID", "drug"]].rename(columns={"drug": "exposure"}).drop_duplicates()

    ind = read_cv(raw, "report_drug_indication", ["REPORT_DRUG_ID", "INDICATION_NAME_ENG"])
    ket = rd[rd["drug"] == "ketamine"][["REPORT_ID", "REPORT_DRUG_ID"]].merge(ind, on="REPORT_DRUG_ID", how="left")
    ket["group"] = ket["INDICATION_NAME_ENG"].map(ketamine_indication)
    known = set(ket.loc[ket["group"] != "unknown", "REPORT_ID"])
    ket = ket[(ket["group"] != "unknown") | ~ket["REPORT_ID"].isin(known)]
    expo = pd.concat([expo, pd.DataFrame({"REPORT_ID": ket["REPORT_ID"],
                                          "exposure": "ketamine: " + ket["group"]})]).drop_duplicates()

    reac = read_cv(raw, "reactions", ["REPORT_ID", "PT_NAME_ENG", "SOC_NAME_ENG"])
    reac = reac[reac["REPORT_ID"].isin(ids)].dropna(subset=["PT_NAME_ENG"])
    return rep, expo, reac


def signals(rep, expo, reac):
    """Same 2 x 2 tables as 04_signals.py, computed in pandas."""
    r = reac[["REPORT_ID", "PT_NAME_ENG"]].rename(columns={"PT_NAME_ENG": "pt"})
    r["pt_key"] = r["pt"].str.upper()
    names = r.drop_duplicates("pt_key").set_index("pt_key")["pt"]
    r = r[["REPORT_ID", "pt_key"]].drop_duplicates()
    total = rep["REPORT_ID"].nunique()

    n_pt = r.groupby("pt_key").size().rename("n_pt")
    n_x = expo.groupby("exposure").size().rename("n_x")
    a = expo.merge(r, on="REPORT_ID").groupby(["exposure", "pt_key"]).size().rename("a").reset_index()
    base = a.join(n_x, on="exposure")

    full = base.join(n_pt, on="pt_key")
    full["b"] = full["n_x"] - full["a"]
    full["c"] = full["n_pt"] - full["a"]
    full["d"] = total - full["n_x"] - full["c"]
    full["background"] = "All Canada Vigilance"

    pool = set(expo.loc[expo["exposure"].isin(COMPARATORS), "REPORT_ID"])
    rp = r[r["REPORT_ID"].isin(pool)]
    n_pt_comp = rp.groupby("pt_key").size().rename("n_pt_comp")
    frames = [full]
    for exp in sorted(set(expo["exposure"]) - set(COMPARATORS)):
        xs = set(expo.loc[expo["exposure"] == exp, "REPORT_ID"])
        ov = xs & pool
        ov_pt = rp[rp["REPORT_ID"].isin(ov)].groupby("pt_key").size().rename("ov_pt")
        s = base[base["exposure"] == exp].join(n_pt_comp, on="pt_key").join(ov_pt, on="pt_key")
        s = s.fillna({"n_pt_comp": 0, "ov_pt": 0})
        s["b"] = s["n_x"] - s["a"]
        s["c"] = s["n_pt_comp"] - s["ov_pt"]
        s["d"] = (len(pool) - len(ov)) - s["c"]
        s["background"] = "Other antidepressants"
        frames.append(s)

    out = pd.concat(frames, ignore_index=True)
    out["pt"] = out["pt_key"].map(names)
    out = stats(out[["exposure", "background", "pt", "a", "b", "c", "d"]].astype(
        {k: int for k in "abcd"}))
    out.insert(3, "term_category", out["pt"].map(term_category))
    return out.sort_values(["exposure", "background", "a"], ascending=[True, True, False])


def pt_soc(reac):
    """Most common organ class for each reaction term (MedDRA primary SOC in practice)."""
    s = reac.dropna(subset=["SOC_NAME_ENG"]).assign(pt_key=reac["PT_NAME_ENG"].str.upper())
    s = s.groupby(["pt_key", "SOC_NAME_ENG"]).size().rename("n").reset_index()
    s = s.sort_values(["pt_key", "n"], ascending=[True, False]).drop_duplicates("pt_key")
    return s.rename(columns={"SOC_NAME_ENG": "soc"})[["pt_key", "soc"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(RAW_CV))
    ap.add_argument("--db", default=None)
    ap.add_argument("--out", default=str(OUTPUTS))
    args = ap.parse_args()
    out = Path(args.out)

    rep, expo, reac = load(args.raw)
    sig = signals(rep, expo, reac)
    by_year = (expo.merge(rep[["REPORT_ID", "received"]], on="REPORT_ID")
                   .assign(year=lambda d: d["received"].dt.year)
                   .groupby(["exposure", "year"]).size().rename("reports").reset_index())
    soc = pt_soc(reac)

    con = connect(args.db)
    rep.drop(columns=["received"]).to_sql("cv_report", con, if_exists="replace", index=False)
    expo.to_sql("cv_exposure_report", con, if_exists="replace", index=False)
    sig.to_sql("cv_signals", con, if_exists="replace", index=False)
    con.close()

    sig.to_csv(out / "cv_signals.csv", index=False)
    by_year.to_csv(out / "cv_reports_by_year.csv", index=False)
    soc.to_csv(out / "pt_soc.csv", index=False)

    print("\nReports per exposure:")
    print(expo.groupby("exposure").size().to_string())
    flagged = sig[sig["signal_ror"]].groupby(["exposure", "background"]).size()
    print("\nPairs flagged by ROR:")
    print(flagged.to_string())


if __name__ == "__main__":
    main()
