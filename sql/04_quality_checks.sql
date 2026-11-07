-- Data quality checks
SET search_path = hfa;

-- Q1. Coverage: year span and completeness of each indicator at each level.
-- Completeness = observed rows / (geographies x years in the span).
WITH cov AS (
    SELECT i.short_name,
           CASE WHEN o.province_code IS NOT NULL THEN 'province' ELSE 'region' END AS geo_level,
           min(o.year) AS first_year,
           max(o.year) AS last_year,
           count(DISTINCT coalesce(o.province_code, o.region_num::text)) AS n_geo,
           count(*) AS n_obs
    FROM observation o
    JOIN indicator i USING (indicator_id)
    GROUP BY 1, 2
)
SELECT short_name, geo_level, first_year, last_year, n_geo, n_obs,
       round(100.0 * n_obs / ((CASE geo_level WHEN 'province' THEN 110 ELSE 20 END)
                              * (last_year - first_year + 1)), 1) AS pct_complete
FROM cov
ORDER BY short_name, geo_level;

-- Q2. Gaps: province series with missing years inside their observed span.
-- Uses LAG to compare each year with the previous observed year.
WITH s AS (
    SELECT i.short_name, p.province_name, o.year,
           lag(o.year) OVER (PARTITION BY o.indicator_id, o.province_code ORDER BY o.year) AS prev_year
    FROM observation o
    JOIN indicator i USING (indicator_id)
    JOIN province  p USING (province_code)
)
SELECT short_name, province_name,
       prev_year + 1 AS gap_from,
       year - 1      AS gap_to
FROM s
WHERE year - prev_year > 1
ORDER BY short_name, province_name, gap_from;

-- Q3. Validation: do province values add up to Istat's region totals?
-- Rows where the two differ by more than 0.5% are listed.
WITH prov_sum AS (
    SELECT p.region_num, o.indicator_id, o.year,
           sum(o.value) AS province_sum,
           count(*)     AS n_provinces
    FROM observation o
    JOIN province p USING (province_code)
    GROUP BY 1, 2, 3
),
expected AS (
    SELECT region_num, count(*) AS n_expected FROM province GROUP BY 1
)
SELECT r.region_name, i.short_name, ps.year,
       ps.n_provinces, e.n_expected,
       ps.province_sum, o.value AS region_total,
       round(100 * (ps.province_sum - o.value) / NULLIF(o.value, 0), 2) AS pct_diff
FROM prov_sum ps
JOIN observation o ON o.region_num = ps.region_num
                  AND o.indicator_id = ps.indicator_id
                  AND o.year = ps.year
JOIN region    r ON r.region_num = ps.region_num
JOIN indicator i ON i.indicator_id = ps.indicator_id
JOIN expected  e ON e.region_num = ps.region_num
WHERE abs(ps.province_sum - o.value) > 0.005 * o.value
ORDER BY abs(ps.province_sum - o.value) / NULLIF(o.value, 0) DESC
LIMIT 25;

-- Q4. Outliers: year-over-year jumps of more than 40% in province counts,
-- which usually signal reporting changes rather than real change.
WITH yoy AS (
    SELECT i.short_name, p.province_name, o.year, o.value,
           lag(o.value) OVER w AS prev_value,
           lag(o.year)  OVER w AS prev_year
    FROM observation o
    JOIN indicator i USING (indicator_id)
    JOIN province  p USING (province_code)
    WHERE i.short_name <> 'population'
    WINDOW w AS (PARTITION BY o.indicator_id, o.province_code ORDER BY o.year)
)
SELECT short_name, province_name, prev_year, year, prev_value, value,
       round(100 * (value - prev_value) / NULLIF(prev_value, 0), 1) AS pct_change
FROM yoy
WHERE year = prev_year + 1
  AND prev_value >= 50
  AND abs(value - prev_value) > 0.4 * prev_value
ORDER BY abs(value - prev_value) / prev_value DESC
LIMIT 25;
