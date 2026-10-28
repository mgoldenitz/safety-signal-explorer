"""Shared settings and helpers for the Safety Signal Explorer pipeline.

Raw downloads and the SQLite database live outside the repo (and outside
OneDrive, where SQLite builds fail). Set SSX_DATA to change the location;
the default is ~/ssx_data.
"""

import os
import re
import sqlite3
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("SSX_DATA", Path.home() / "ssx_data"))
RAW_FAERS = DATA / "raw" / "faers"
DB_PATH = DATA / "ssx.sqlite"
OUTPUTS = REPO / "outputs"

# Esketamine was approved in the US in March 2019, so 2019 Q1 is the first
# quarter in which esketamine and the comparators share a reporting period.
START_QUARTER = "2019Q1"

# Only suspect drugs count (FAERS role codes): primary and secondary suspect.
SUSPECT_ROLES = ("PS", "SS")

# Drug groups. Each generic name matches on whole words in the active
# ingredient (prod_ai) or the verbatim drug name, so "KETAMINE" does not match
# "ESKETAMINE", "CITALOPRAM" does not match "ESCITALOPRAM", and "VENLAFAXINE"
# does not match "DESVENLAFAXINE". Brand names catch reports with no prod_ai.
DRUGS = {
    # generic: (group, [names to match])
    "esketamine": ("Study drug", ["ESKETAMINE", "SPRAVATO"]),
    "ketamine": ("Study drug", ["KETAMINE", "KETALAR"]),
    "sertraline": ("SSRI", ["SERTRALINE", "ZOLOFT"]),
    "escitalopram": ("SSRI", ["ESCITALOPRAM", "LEXAPRO", "CIPRALEX"]),
    "citalopram": ("SSRI", ["CITALOPRAM", "CELEXA"]),
    "fluoxetine": ("SSRI", ["FLUOXETINE", "PROZAC"]),
    "paroxetine": ("SSRI", ["PAROXETINE", "PAXIL"]),
    "venlafaxine": ("SNRI", ["VENLAFAXINE", "EFFEXOR"]),
    "desvenlafaxine": ("SNRI", ["DESVENLAFAXINE", "PRISTIQ"]),
    "duloxetine": ("SNRI", ["DULOXETINE", "CYMBALTA"]),
    "bupropion": ("Other antidepressant", ["BUPROPION", "WELLBUTRIN", "ZYBAN"]),
    "mirtazapine": ("Other antidepressant", ["MIRTAZAPINE", "REMERON"]),
    "vortioxetine": ("Other antidepressant", ["VORTIOXETINE", "TRINTELLIX", "BRINTELLIX"]),
    "trazodone": ("Other antidepressant", ["TRAZODONE", "DESYREL", "OLEPTRO"]),
}
STUDY_DRUGS = [d for d, (g, _) in DRUGS.items() if g == "Study drug"]
COMPARATORS = [d for d, (g, _) in DRUGS.items() if g != "Study drug"]

_PATTERNS = {
    drug: re.compile(r"\b(" + "|".join(names) + r")\b") for drug, (_, names) in DRUGS.items()
}


def match_drugs(text):
    """Return the set of generic names found in a drug name or ingredient string."""
    if not isinstance(text, str) or not text:
        return set()
    text = text.upper()
    return {drug for drug, pat in _PATTERNS.items() if pat.search(text)}


# Ketamine is used mostly in anaesthesia, so its reports are split by the
# indication given for the ketamine drug row. Checked in this order; the first
# match wins. Terms are MedDRA preferred terms as they appear in FAERS.
KETAMINE_INDICATION_RULES = [
    ("unknown", ["PRODUCT USED FOR UNKNOWN INDICATION", "UNKNOWN"]),
    ("psychiatric", ["DEPRESSION", "SUICIDAL", "BIPOLAR", "MOOD", "ANXIETY",
                    "POST-TRAUMATIC STRESS", "OBSESSIVE"]),
    ("anaesthesia or sedation", ["ANAESTHESIA", "ANESTHESIA", "SEDATION", "SURGERY",
                                 "INTUBATION", "PROCEDUR", "AGITATION", "SEIZURE",
                                 "STATUS EPILEPTICUS", "MECHANICAL VENTILATION"]),
    ("pain", ["PAIN", "ANALGESI", "COMPLEX REGIONAL"]),
]


def ketamine_indication(indi_pt):
    if not isinstance(indi_pt, str) or not indi_pt.strip():
        return "unknown"
    t = indi_pt.upper()
    for label, keys in KETAMINE_INDICATION_RULES:
        if any(k in t for k in keys):
            return label
    return "other"


def quarters(start, end):
    """Yield quarter labels like '2019Q1' from start to end inclusive."""
    y, q = int(start[:4]), int(start[-1])
    ey, eq = int(end[:4]), int(end[-1])
    while (y, q) <= (ey, eq):
        yield f"{y}Q{q}"
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)


def connect(path=None):
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


# FAERS has no MedDRA hierarchy, so reaction terms that describe a product,
# device, use or administrative event rather than a clinical reaction are
# labelled by keyword. The dashboard shows clinical terms by default.
_NON_CLINICAL = [
    ("Lack of effect", ["DRUG INEFFECTIVE", "THERAPEUTIC PRODUCT EFFECT", "THERAPEUTIC RESPONSE",
                        "TREATMENT FAILURE", "LACK OF EFFICACY", "NON-RESPONDER",
                        "EFFECT LESS THAN EXPECTED", "EFFECT INCOMPLETE", "LACK OF CONCOMITANT"]),
    ("Product, device or use", ["DEVICE", "PRODUCT", "MEDICATION ERROR", "OFF LABEL",
                                "WRONG ", "INCORRECT ", "UNDERDOSE", "NONCOMPLIANCE",
                                "NON-COMPLIANCE", "INTERCEPTED", "EXPOSURE ", "EXPOSURE VIA",
                                "INAPPROPRIATE SCHEDULE", "EXTRA DOSE", "DOSE OMISSION",
                                "PRESCRIBED", "DRUG DOSE", "DRUG ADMINISTRATION",
                                "CIRCUMSTANCE OR INFORMATION", "INSURANCE", "LABELLED DRUG",
                                "UNAPPROVED INDICATION", "DELIVERY SYSTEM", "MONITORING PROCEDURE",
                                "ISSUE", "TITRATION ERROR", "WITHOUT A PRESCRIPTION", " USER "]),
    ("Procedure or administrative", ["HOSPITALISATION", "SURGERY", "OPERATION",
                                     "PHYSICAL EXAMINATION", "NO ADVERSE EVENT",
                                     "ADVERSE EVENT", "ADVERSE DRUG REACTION", "THERAPY CESSATION",
                                     "THERAPY INTERRUPTED", "THERAPY CHANGE", "TREATMENT DELAYED",
                                     "DEATH", "PROCEDURE ", "THERAPY ", "CHEMOTHERAPY", "RADIOTHERAPY"]),
]
_CLINICAL_EXCEPTIONS = ["OVERDOSE", "SUDDEN DEATH", "SUDDEN CARDIAC DEATH", "BRAIN DEATH"]


def term_category(pt):
    """Clinical, or one of the non-clinical groups above."""
    t = str(pt).upper() + " "
    if any(x in t for x in _CLINICAL_EXCEPTIONS):
        return "Clinical"
    for label, keys in _NON_CLINICAL:
        if any(k in t for k in keys):
            return label
    return "Clinical"


def stats(df):
    """Add PRR, ROR, IC and signal flags to a frame with columns a, b, c, d."""
    a, b, c, d = (df[k].astype(float) for k in "abcd")
    n = a + b + c + d
    with np.errstate(divide="ignore", invalid="ignore"):
        prr = (a / (a + b)) / (c / (c + d))
        se_prr = np.sqrt(1 / a - 1 / (a + b) + 1 / c - 1 / (c + d))
        ror = (a * d) / (b * c)
        se_ror = np.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
        chi2 = n * (np.abs(a * d - b * c) - n / 2).clip(lower=0) ** 2 / (
            (a + b) * (c + d) * (a + c) * (b + d))
        expected = (a + b) * (a + c) / n
        ic = np.log2((a + 0.5) / (expected + 0.5))
        ic025 = ic - 3.3 * (a + 0.5) ** -0.5 - 2 * (a + 0.5) ** -1.5
    out = df.copy()
    out["expected"] = expected
    out["prr"] = prr
    out["prr_lo"] = np.exp(np.log(prr) - 1.96 * se_prr)
    out["prr_hi"] = np.exp(np.log(prr) + 1.96 * se_prr)
    out["chi2"] = chi2
    out["ror"] = ror
    out["ror_lo"] = np.exp(np.log(ror) - 1.96 * se_ror)
    out["ror_hi"] = np.exp(np.log(ror) + 1.96 * se_ror)
    out["ic"] = ic
    out["ic025"] = ic025
    out["signal_evans"] = (a >= 3) & (prr >= 2) & (chi2 >= 4)
    out["signal_ror"] = (a >= 3) & (out["ror_lo"] > 1)
    out["signal_ic"] = ic025 > 0
    return out.replace([np.inf, -np.inf], np.nan)
