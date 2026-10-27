"""De-duplicate reports and build one row per report and exposure.

Runs sql/03_deduplicate.sql, then labels each ketamine report by indication
(psychiatric, anaesthesia or sedation, pain, other, unknown) and adds those
as extra exposures named "ketamine: <indication>". A ketamine report with
more than one indication group gets each one.
"""

import argparse

import pandas as pd

from common import REPO, connect, ketamine_indication


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    args = ap.parse_args()
    con = connect(args.db)

    con.executescript((REPO / "sql" / "03_deduplicate.sql").read_text())

    ket = pd.read_sql(
        """SELECT DISTINCT e.primaryid, e.drug_seq, i.indi_pt
           FROM exposure e
           JOIN report r USING (primaryid)
           LEFT JOIN indi i ON i.primaryid = e.primaryid AND i.drug_seq = e.drug_seq
           WHERE e.drug = 'ketamine'""",
        con,
    )
    ket["group"] = ket["indi_pt"].map(ketamine_indication)
    # A report with any known indication is not also "unknown".
    known = set(ket.loc[ket["group"] != "unknown", "primaryid"])
    ket = ket[(ket["group"] != "unknown") | ~ket["primaryid"].isin(known)]
    rows = ket[["primaryid"]].assign(exposure="ketamine: " + ket["group"]).drop_duplicates()
    con.executemany("INSERT OR IGNORE INTO exposure_report VALUES (?, ?)", rows.itertuples(index=False))
    con.commit()

    n_demo = con.execute("SELECT COUNT(*) FROM demo").fetchone()[0]
    n_rep = con.execute("SELECT COUNT(*) FROM report").fetchone()[0]
    print(f"{n_demo:,} report versions loaded, {n_rep:,} cases kept after de-duplication")
    for exp, n in con.execute(
        "SELECT exposure, COUNT(*) FROM exposure_report GROUP BY exposure ORDER BY exposure"
    ):
        print(f"  {exp:<35} {n:>9,}")
    con.close()


if __name__ == "__main__":
    main()
