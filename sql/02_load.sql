-- Load the CSVs written by src/export_csv.py.
-- Run from the repository root:  psql -d italy_health -f sql/02_load.sql
SET search_path = hfa;

\copy region    FROM 'data/region.csv'    WITH (FORMAT csv, HEADER true)
\copy province  FROM 'data/province.csv'  WITH (FORMAT csv, HEADER true)
\copy indicator FROM 'data/indicator.csv' WITH (FORMAT csv, HEADER true)

-- observations arrive in one long file; stage them, then route each row to
-- the province or region column
CREATE TEMP TABLE stage_observation (
    geo_level    text,
    geo_code     text,
    indicator_id smallint,
    year         smallint,
    value        numeric
);
\copy stage_observation FROM 'data/observation.csv' WITH (FORMAT csv, HEADER true)

INSERT INTO observation (province_code, region_num, indicator_id, year, value)
SELECT CASE WHEN geo_level = 'province' THEN geo_code END,
       CASE WHEN geo_level = 'region'   THEN geo_code::smallint END,
       indicator_id, year, value
FROM stage_observation;

ANALYZE;

SELECT 'region' AS table_name, count(*) FROM region
UNION ALL SELECT 'province',    count(*) FROM province
UNION ALL SELECT 'indicator',   count(*) FROM indicator
UNION ALL SELECT 'observation', count(*) FROM observation;
