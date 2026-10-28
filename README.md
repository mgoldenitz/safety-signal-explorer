# Safety Signal Explorer

Which adverse reactions are reported more often than expected for esketamine (Spravato) and ketamine, compared with all other reports and with 12 other antidepressants?

The analysis uses 10.8 million de-duplicated FDA Adverse Event Reporting System (FAERS) cases from 2019 Q1 to 2026 Q2 and 567,733 Health Canada Canada Vigilance reports from the same period. All 8 known reactions used as positive controls were flagged, and none of the 4 negative controls were. Against other antidepressants, esketamine has 93 clinical reaction terms reported more often than expected. Dissociation leads with a reporting odds ratio (ROR) of 119.

In short: the pipeline finds what the Spravato label already lists, which shows it works, and it points to a handful of reactions worth a closer look. Spontaneous reports show that a reaction is reported more often with a drug. They do not show how often it happens or that the drug caused it.

## Question and design

Each drug and reaction pair gets a 2 x 2 table of report counts:

|  | Reaction | Other reactions |
| --- | --- | --- |
| Drug | a | b |
| Other reports | c | d |

"Other reports" has two versions. The first is every other report in the database. The second, used for esketamine and ketamine, is reports naming one of 12 comparator antidepressants (sertraline, escitalopram, citalopram, fluoxetine, paroxetine, venlafaxine, desvenlafaxine, duloxetine, bupropion, mirtazapine, vortioxetine, trazodone), minus reports that also name the study drug. The comparator version reduces confounding by indication: people given esketamine have treatment-resistant depression, and comparing them with other people taking antidepressants takes some of that out.

Ketamine reports are also split by the indication given for ketamine (psychiatric, anaesthesia or sedation, pain, other, unknown), because most ketamine use is in anaesthesia.

## Data

| Source | Period | Size after cleaning |
| --- | --- | --- |
| FAERS quarterly ASCII files (FDA) | 2019 Q1 to 2026 Q2, 30 quarters | 12,902,877 report versions reduced to 10,825,833 cases |
| Canada Vigilance data extract (Health Canada), dated 30 June 2026 | Reports first received from 2019 | 567,733 reports after removing 26,988 linked duplicates |

FAERS de-duplication keeps the latest version of each case (highest case version, then latest FDA date) and removes cases on the FDA's deleted list. Only drugs listed as primary or secondary suspect count; concomitant drugs do not. Drug names are matched on whole words in the active ingredient and the verbatim name, so "KETAMINE" does not match "ESKETAMINE".

| Drug | FAERS reports | Canada Vigilance reports |
| --- | --- | --- |
| Esketamine | 18,068 | 19 |
| Ketamine (all uses) | 7,186 | 200 |
| Ketamine, psychiatric use | 251 | 10 |
| Sertraline | 40,946 | 1,056 |
| Venlafaxine | 31,497 | 1,587 |
| Bupropion | 32,970 | 2,514 |

Canada Vigilance holds 29 Spravato drug rows in its whole extract, which leaves 19 reports from 2019 onward. That is too few for disproportionality analysis, so the Canadian comparison covers ketamine and the comparators only.

FAERS has no MedDRA hierarchy. Canada Vigilance codes each reaction to a MedDRA organ class, so the organ class for each term comes from there (`pt_soc.csv`); it covers 95% of FAERS drug-reaction pairs. Terms that describe a product, device, procedure or lack of effect ("Device issue", "Hospitalisation", "Drug ineffective") are labelled by keyword rules in `scripts/common.py` and left out of the clinical results.

## Measures

- Reporting odds ratio, ROR = (a/b) / (c/d), with a 95% confidence interval. A signal is a reaction with at least 3 reports and a lower bound above 1.
- Proportional reporting ratio, PRR = (a/(a+b)) / (c/(c+d)), with the Evans criteria: PRR at least 2, chi-squared (Yates) at least 4, at least 3 reports.
- Information component (IC) with the IC025 approximation; a signal when IC025 is above 0.

The ROR is the main measure; the other two are in `signals.csv` for comparison.

## Validation

Checked against all of FAERS before any result was read.

| Control | Expected | Reports | ROR (95% CI) | Result |
| --- | --- | --- | --- | --- |
| Esketamine: dissociation | Signal | 3,691 | 1,819 (1,710 to 1,935) | Flagged |
| Esketamine: sedation | Signal | 2,654 | 181 (173 to 189) | Flagged |
| Esketamine: suicidal ideation | Signal | 1,437 | 26.0 (24.6 to 27.5) | Flagged |
| Esketamine: blood pressure increased | Signal | 568 | 4.56 (4.19 to 4.96) | Flagged |
| Esketamine: dizziness | Signal | 655 | 1.77 (1.64 to 1.92) | Flagged |
| Esketamine: vertigo | Signal | 103 | 2.36 (1.94 to 2.87) | Flagged |
| Esketamine: feeling drunk | Signal | 75 | 17.5 (13.9 to 22.0) | Flagged |
| Ketamine: cystitis terms | Signal | 163 | 753 (304 to 1,867) | Flagged |
| Esketamine: cataract | No signal | 17 | 0.32 (0.20 to 0.51) | Not flagged |
| Esketamine: rotator cuff syndrome | No signal | 5 | 0.56 (0.23 to 1.34) | Not flagged |
| Esketamine: osteoarthritis | No signal | 3 | 0.09 (0.03 to 0.27) | Not flagged |
| Esketamine: gout | No signal | 0 | none | Not flagged |

The first seven are on the Spravato label; ketamine bladder damage is well documented. Gout had no esketamine reports, so it tests nothing.

## Results

Esketamine against the 12 comparator antidepressants: 93 clinical terms flagged, 22 of them psychiatric and 11 nervous system terms. 72 clinical terms are flagged against both comparison groups.

| Reaction | Organ class | Reports | ROR (95% CI) |
| --- | --- | --- | --- |
| Dissociation | Psychiatric | 3,691 | 119 (108 to 131) |
| Nasal discomfort | Respiratory | 73 | 23.5 (15.8 to 34.9) |
| Sedation | Nervous system | 2,654 | 22.2 (20.8 to 23.6) |
| Oxygen saturation abnormal | Investigations | 82 | 17.2 (12.2 to 24.1) |
| Dissociative disorder | Psychiatric | 93 | 13.4 (9.9 to 18.0) |
| Intracranial aneurysm | Nervous system | 11 | 10.9 (4.8 to 24.7) |
| Psychogenic seizure | Nervous system | 26 | 9.7 (5.8 to 16.2) |
| Flashback | Psychiatric | 19 | 9.0 (5.0 to 16.4) |
| Anaphylactic shock | Immune system | 41 | 5.9 (4.1 to 8.7) |
| Neoplasm malignant | Neoplasms | 83 | 5.8 (4.4 to 7.5) |
| Cystitis interstitial | Renal and urinary | 12 | 5.1 (2.6 to 10.0) |
| Blood pressure increased | Investigations | 568 | 3.6 (3.2 to 3.9) |
| Suicidal ideation | Psychiatric | 1,437 | 2.7 (2.5 to 2.8) |

Most of the top terms are on the label or follow from how the drug is given: a nasal spray, with blood pressure and oxygen checks in the clinic. Interstitial cystitis matches the bladder damage known for ketamine. Intracranial aneurysm (11 reports) connects to the blood pressure rise: the Spravato label lists aneurysmal vascular disease as a contraindication. Eleven reports cannot show more than that. Anaphylactic shock and malignant neoplasm are the least expected; both need a look at the individual reports before anything is said about them.

Ketamine with a psychiatric indication (251 reports) against the comparators: dissociation (28 reports, ROR 59), suicidal ideation (21, 2.8), mania (10, 7.3) and reversible cerebral vasoconstriction syndrome (10, 12.5). Ketamine given for anaesthesia or sedation is dominated by perioperative reactions, led by anaphylactic shock (505 reports, ROR 212), which most likely reflects other drugs given during surgery rather than ketamine.

The 2025 study of esketamine in FAERS (European Journal of Clinical Pharmacology, 82(1)) used 7,790 reports to the end of 2024 and found 173 ROR signals. This project has 9,945 esketamine reports to the end of 2024 and 249 ROR signals over the full period, using a different de-duplication rule, suspect roles and end date.

## Limitations

- Spontaneous reports show association, not incidence or causation. There is no count of people exposed to each drug.
- Confounding by indication remains for psychiatric terms, even against other antidepressants, because treatment-resistant depression is more severe than the depression most comparators treat.
- Spravato is given under supervision in certified clinics with required monitoring, which likely raises its reporting.
- Esketamine reports jumped from about 1,000 a quarter to 2,444 in 2025 Q2. A burst of reports from one source can create or inflate signals.
- Esketamine is also used intravenously as an anaesthetic outside North America, and FAERS includes foreign reports. Some esketamine reports, especially the perioperative ones, may not be Spravato. Splitting by route is the next step.
- The term categories and the organ-class lookup are approximations of the MedDRA hierarchy, which needs a licence.
- 466 of 51,168 FAERS drug-reaction pairs (0.9%) have no ROR because no other report has that reaction (c = 0).

## Run it (WSL)

```bash
cd /mnt/c/Users/mgold/OneDrive/Desktop/Career/safety-signal-explorer
~/brainenv/bin/python -m pip install -r requirements.txt
~/brainenv/bin/python -m pytest -q tests          # 11 tests on hand-made files
bash run_all.sh ~/brainenv/bin/python
```

`run_all.sh` downloads every FAERS quarter from 2019 Q1 (about 30 zip files of 50 to 90 MB), loads them into SQLite, de-duplicates, computes the statistics, runs validation and writes CSVs to `outputs/`. Raw files and the database go to `~/ssx_data` inside WSL, outside OneDrive, because SQLite builds fail in the OneDrive folder. Set `SSX_DATA` to use another location. For the Canadian step, download the extract from Health Canada's "Data extracts from the Canada Vigilance adverse reaction online database" page and unzip it into `~/ssx_data/raw/canada_vigilance` before running.

| Script | Does |
| --- | --- |
| `01_download_faers.py` | Downloads the FAERS quarterly ASCII files |
| `02_load_faers.py` | Loads reports, reactions, matched suspect drugs, ketamine indications, outcomes and deleted cases |
| `03_deduplicate.py` | Keeps the latest version of each case and splits ketamine reports by indication |
| `04_signals.py` | Builds the 2 x 2 counts in SQL and computes ROR, PRR and IC |
| `05_validate.py` | Checks the positive and negative controls |
| `06_export.py` | Writes tables for Power BI |
| `07_canada_vigilance.py` | Loads Canada Vigilance, computes the same signals and the organ-class lookup |

## Sources

- FDA, FAERS quarterly data extract files.
- Health Canada, Canada Vigilance Adverse Reaction Online Database data extract and "Data Structure" page.
- The Reporting of a Disproportionality Analysis for Drug Safety Signal Detection Using Individual Case Safety Reports in PharmacoVigilance (READUS-PV): Development and Statement. Drug Safety 2024;47(6):575 to 584.
- A real-world pharmacovigilance study of adverse events associated with esketamine: disproportionality analysis and detection of potential drug-drug interaction signals. European Journal of Clinical Pharmacology 2025;82(1).
