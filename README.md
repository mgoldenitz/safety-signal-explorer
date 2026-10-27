# Safety Signal Explorer

Which adverse reactions are reported more often than expected for esketamine (Spravato) and ketamine, compared with all of FAERS and with 12 other antidepressants?

This README covers setup and running for now. Results, methods and limitations will be added once the full data has run.

## Run it (WSL)

```bash
cd /mnt/c/Users/mgold/OneDrive/Desktop/Career/safety-signal-explorer
~/brainenv/bin/python -m pip install -r requirements.txt
~/brainenv/bin/python -m pytest -q tests          # 8 tests on hand-made files
bash run_all.sh ~/brainenv/bin/python
```

`run_all.sh` downloads every FAERS quarter from 2019 Q1 to the latest one (about 30 zip files of 50 to 90 MB each), loads them into SQLite, removes duplicate case versions and deleted cases, computes the statistics, runs the validation checks and writes CSVs to `outputs/`. Raw files and the database go to `~/ssx_data` inside WSL, outside OneDrive, because SQLite builds fail in the OneDrive folder. Set `SSX_DATA` to use another location.

Each step can be run on its own, and steps 01 and 02 skip quarters already done, so an interrupted run can be restarted.

| Script | Does |
| --- | --- |
| `01_download_faers.py` | Downloads the FAERS quarterly ASCII files |
| `02_load_faers.py` | Loads reports, reactions, matched suspect drugs, ketamine indications, outcomes and deleted cases |
| `03_deduplicate.py` | Keeps the latest version of each case and splits ketamine reports by indication |
| `04_signals.py` | Builds the 2 x 2 counts in SQL and computes PRR, ROR and IC with signal flags |
| `05_validate.py` | Checks Spravato label reactions, ketamine cystitis and negative controls |
| `06_export.py` | Writes tidy tables for Power BI |
