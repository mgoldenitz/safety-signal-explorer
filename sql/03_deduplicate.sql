-- Keep one report per case: the latest version (highest caseversion, then the
-- latest FDA date, then the highest primaryid). Cases the FDA has deleted are
-- dropped. Everything downstream counts reports from this table only.
DROP TABLE IF EXISTS report;
CREATE TABLE report AS
SELECT primaryid, caseid, caseversion, fda_dt, quarter, sex, age_years, occr_country, rept_cod
FROM (
    SELECT d.*,
           ROW_NUMBER() OVER (PARTITION BY caseid
                              ORDER BY caseversion DESC, fda_dt DESC, primaryid DESC) AS rn
    FROM demo d
    WHERE caseid IS NOT NULL
)
WHERE rn = 1
  AND caseid NOT IN (SELECT caseid FROM deleted);
CREATE UNIQUE INDEX ix_report ON report (primaryid);

-- One row per report and exposure. Each of the 14 drugs is an exposure, and
-- ketamine reports are also split by the indication given for ketamine. A
-- ketamine report with no indication row is "unknown".
DROP TABLE IF EXISTS exposure_report;
CREATE TABLE exposure_report (primaryid INTEGER, exposure TEXT, PRIMARY KEY (primaryid, exposure)) WITHOUT ROWID;

INSERT OR IGNORE INTO exposure_report
SELECT DISTINCT e.primaryid, e.drug
FROM exposure e JOIN report r USING (primaryid);

-- Ketamine indication groups are filled in by 03_deduplicate.py, which applies
-- the rules in common.py to the indi table.
