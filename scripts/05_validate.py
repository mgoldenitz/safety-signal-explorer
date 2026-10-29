"""Check the signals against reactions whose answer is already known.

Positive controls are reactions listed on the Spravato label and ketamine's
known bladder damage. Each should be flagged against all of FAERS. If one is
not, the pipeline is more likely wrong than the label.

Negative controls are reactions with no plausible link to esketamine. They
should not be flagged. A flagged negative control is a warning: it can
happen by chance with this many tests, but it should be looked at.

Writes outputs/validation.csv and exits with code 1 if a positive control fails.
"""

import argparse
import sys

import pandas as pd

from common import OUTPUTS, connect

# (exposure, reaction term or terms, expected, source). For a list of terms the
# control passes if any one of them is flagged.
CONTROLS = [
    ("esketamine", ["Dissociation"], True, "Spravato label: boxed warning"),
    ("esketamine", ["Sedation", "Somnolence"], True, "Spravato label: boxed warning"),
    ("esketamine", ["Blood pressure increased"], True, "Spravato label: warnings"),
    ("esketamine", ["Dizziness"], True, "Spravato label: common adverse reaction"),
    ("esketamine", ["Vertigo"], True, "Spravato label: common adverse reaction"),
    ("esketamine", ["Feeling drunk"], True, "Spravato label: common adverse reaction"),
    ("esketamine", ["Suicidal ideation"], True, "Spravato label: boxed warning (also confounded by indication)"),
    ("ketamine", ["Cystitis", "Cystitis interstitial", "Cystitis noninfective",
                  "Cystitis haemorrhagic", "Cystitis ulcerative"], True, "Ketamine-induced uropathy"),
    ("esketamine", ["Cataract"], False, "Negative control"),
    ("esketamine", ["Cholelithiasis"], False, "Negative control"),
    ("esketamine", ["Rotator cuff syndrome"], False, "Negative control"),
    ("esketamine", ["Diabetes mellitus"], False, "Negative control"),
]


def check(sig, background="All FAERS", flag="signal_ror"):
    rows = []
    s = sig[sig["background"] == background].copy()
    s["pt_key"] = s["pt"].str.upper()
    for exposure, terms, expected, source in CONTROLS:
        keys = [t.upper() for t in terms]
        hit = s[(s["exposure"] == exposure) & s["pt_key"].isin(keys)]
        best = hit.sort_values("ror_lo", ascending=False).head(1)
        flagged = bool(hit[flag].any())
        rows.append({
            "exposure": exposure,
            "reaction": " / ".join(terms),
            "expected_signal": expected,
            "flagged": flagged,
            "passed": flagged == expected,
            "reports": int(hit["a"].sum()) if len(hit) else 0,
            "best_term": best["pt"].iloc[0] if len(best) else None,
            "ror": best["ror"].iloc[0] if len(best) else None,
            "ror_lo": best["ror_lo"].iloc[0] if len(best) else None,
            "ror_hi": best["ror_hi"].iloc[0] if len(best) else None,
            "source": source,
        })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--out", default=str(OUTPUTS / "validation.csv"))
    args = ap.parse_args()
    con = connect(args.db)
    sig = pd.read_sql("SELECT * FROM signals", con)
    con.close()

    res = check(sig)
    res.to_csv(args.out, index=False)
    print(res[["exposure", "reaction", "expected_signal", "flagged", "reports", "ror", "ror_lo"]]
          .to_string(index=False))

    pos_fail = res[res["expected_signal"] & ~res["passed"]]
    neg_fail = res[~res["expected_signal"] & ~res["passed"]]
    if len(neg_fail):
        print(f"\nWarning: {len(neg_fail)} negative control(s) flagged; look at them before publishing.")
    if len(pos_fail):
        print(f"\nFAILED: {len(pos_fail)} positive control(s) not flagged. Check the pipeline first.")
        sys.exit(1)
    print("\nAll positive controls flagged.")


if __name__ == "__main__":
    main()
