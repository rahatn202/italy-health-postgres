-- Analyst-friendly views
SET search_path = hfa;

-- Province observations that fail a quality rule:
--   province_sum_mismatch: every province in the region reported, but their
--                          sum is more than 5% away from Istat's region total
--   isolated_spike:        value jumps more than 40% from both the previous
--                          and the next year (a one-year blip)
CREATE OR REPLACE VIEW suspect_observation AS
WITH n_prov AS (
    SELECT region_num, count(*) AS n_expected FROM province GROUP BY 1
),
prov_sum AS (
    SELECT p.region_num, o.indicator_id, o.year,
           sum(o.value) AS province_sum, count(*) AS n_reported
    FROM observation o JOIN province p USING (province_code)
    GROUP BY 1, 2, 3
),
mismatch AS (
    SELECT o.observation_id, 'province_sum_mismatch'::text AS reason
    FROM prov_sum ps
    JOIN n_prov n USING (region_num)
    JOIN observation r ON r.region_num = ps.region_num
                      AND r.indicator_id = ps.indicator_id AND r.year = ps.year
    JOIN province p ON p.region_num = ps.region_num
    JOIN observation o ON o.province_code = p.province_code
                      AND o.indicator_id = ps.indicator_id AND o.year = ps.year
    WHERE ps.n_reported = n.n_expected
      AND abs(ps.province_sum - r.value) > 0.05 * r.value
),
neighbours AS (
    SELECT observation_id, year, value,
           lag(value)  OVER w AS prev_value, lag(year)  OVER w AS prev_year,
           lead(value) OVER w AS next_value, lead(year) OVER w AS next_year
    FROM observation
    WHERE province_code IS NOT NULL
    WINDOW w AS (PARTITION BY province_code, indicator_id ORDER BY year)
),
spike AS (
    SELECT observation_id, 'isolated_spike'::text AS reason
    FROM neighbours
    WHERE prev_year = year - 1 AND next_year = year + 1
      AND least(prev_value, next_value) >= 50
      AND abs(value - prev_value) > 0.4 * prev_value
      AND abs(value - next_value) > 0.4 * next_value
)
SELECT observation_id, string_agg(reason, ', ' ORDER BY reason) AS reasons
FROM (SELECT * FROM mismatch UNION SELECT * FROM spike) f
GROUP BY observation_id;

-- Wide province x year panel (one column per indicator), the shape most
-- statistical packages expect. Built with conditional aggregation.
-- Values flagged in suspect_observation are left out, so they appear as missing.
CREATE OR REPLACE VIEW province_panel AS
SELECT p.province_code,
       p.province_name,
       r.region_num,
       r.region_name,
       r.macro_area,
       o.year,
       max(o.value) FILTER (WHERE i.short_name = 'population')       AS population,
       max(o.value) FILTER (WHERE i.short_name = 'beds')             AS beds,
       max(o.value) FILTER (WHERE i.short_name = 'nurses_hosp')      AS nurses_hosp,
       max(o.value) FILTER (WHERE i.short_name = 'phys_registered')  AS phys_registered,
       max(o.value) FILTER (WHERE i.short_name = 'phys_spec_active') AS phys_spec_active
FROM observation o
JOIN indicator i USING (indicator_id)
JOIN province  p USING (province_code)
JOIN region    r ON r.region_num = p.region_num
WHERE NOT EXISTS (SELECT 1 FROM suspect_observation s
                  WHERE s.observation_id = o.observation_id)
GROUP BY p.province_code, p.province_name, r.region_num, r.region_name, r.macro_area, o.year;

-- Same panel with rates per 1,000 residents
CREATE OR REPLACE VIEW province_rates AS
SELECT province_code, province_name, region_name, macro_area, year, population,
       round(1000 * beds             / NULLIF(population, 0), 2) AS beds_per1000,
       round(1000 * nurses_hosp      / NULLIF(population, 0), 2) AS nurses_hosp_per1000,
       round(1000 * phys_spec_active / NULLIF(population, 0), 2) AS phys_spec_per1000
FROM province_panel;

-- Region x year panel, including the region-only nurses_ssn series
CREATE OR REPLACE VIEW region_panel AS
SELECT r.region_num,
       r.region_name,
       r.macro_area,
       o.year,
       max(o.value) FILTER (WHERE i.short_name = 'population')       AS population,
       max(o.value) FILTER (WHERE i.short_name = 'beds')             AS beds,
       max(o.value) FILTER (WHERE i.short_name = 'nurses_hosp')      AS nurses_hosp,
       max(o.value) FILTER (WHERE i.short_name = 'nurses_ssn')       AS nurses_ssn,
       max(o.value) FILTER (WHERE i.short_name = 'phys_registered')  AS phys_registered,
       max(o.value) FILTER (WHERE i.short_name = 'phys_spec_active') AS phys_spec_active
FROM observation o
JOIN indicator i USING (indicator_id)
JOIN region    r USING (region_num)
GROUP BY r.region_num, r.region_name, r.macro_area, o.year;
