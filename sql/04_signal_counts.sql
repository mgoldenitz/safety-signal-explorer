-- Report counts for the 2 x 2 tables. All counts are distinct de-duplicated
-- reports (reac has one row per report and reaction term).

-- Reports with each reaction, across all of FAERS
DROP TABLE IF EXISTS n_pt_all;
CREATE TABLE n_pt_all AS
SELECT x.pt_id, COUNT(*) AS n
FROM reac x JOIN report r USING (primaryid)
GROUP BY x.pt_id;

-- Reports with each exposure and reaction (cell a)
DROP TABLE IF EXISTS n_exposure_pt;
CREATE TABLE n_exposure_pt AS
SELECT e.exposure, x.pt_id, COUNT(*) AS a
FROM exposure_report e JOIN reac x USING (primaryid)
GROUP BY e.exposure, x.pt_id;

DROP TABLE IF EXISTS n_exposure;
CREATE TABLE n_exposure AS
SELECT exposure, COUNT(*) AS n FROM exposure_report GROUP BY exposure;

-- The comparator pool: reports with at least one of the 12 comparator
-- antidepressants as a suspect drug. Filled with the drug list by
-- 04_signals.py (the :comparators placeholder).
DROP TABLE IF EXISTS comparator_report;
CREATE TABLE comparator_report AS
SELECT DISTINCT primaryid FROM exposure_report WHERE exposure IN (:comparators);
CREATE UNIQUE INDEX ix_comparator_report ON comparator_report (primaryid);

DROP TABLE IF EXISTS n_pt_comparator;
CREATE TABLE n_pt_comparator AS
SELECT x.pt_id, COUNT(*) AS n
FROM reac x JOIN comparator_report c USING (primaryid)
GROUP BY x.pt_id;

-- Study-drug reports that also name a comparator. These are removed from the
-- comparator pool when that study drug is compared with it.
DROP TABLE IF EXISTS n_overlap_pt;
CREATE TABLE n_overlap_pt AS
SELECT e.exposure, x.pt_id, COUNT(*) AS n
FROM exposure_report e
JOIN comparator_report c USING (primaryid)
JOIN reac x USING (primaryid)
WHERE e.exposure NOT IN (:comparators)
GROUP BY e.exposure, x.pt_id;

DROP TABLE IF EXISTS n_overlap;
CREATE TABLE n_overlap AS
SELECT e.exposure, COUNT(*) AS n
FROM exposure_report e JOIN comparator_report c USING (primaryid)
WHERE e.exposure NOT IN (:comparators)
GROUP BY e.exposure;
