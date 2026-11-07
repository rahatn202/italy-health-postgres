-- Analysis queries
SET search_path = hfa;

-- A1. Hospital beds per 1,000 residents by region, latest year, ranked.
WITH latest AS (SELECT max(year) AS year FROM region_panel WHERE beds IS NOT NULL)
SELECT rank() OVER (ORDER BY 1000 * beds / population DESC) AS rnk,
       region_name, macro_area, year,
       round(1000 * beds / population, 2) AS beds_per1000
FROM region_panel
JOIN latest USING (year)
ORDER BY rnk;

-- A2. Ten-year change in bed supply per 1,000 residents by macro-area.
WITH macro AS (
    SELECT macro_area, year, 1000 * sum(beds) / sum(population) AS beds_per1000
    FROM region_panel
    WHERE year IN (2013, 2023)
    GROUP BY 1, 2
)
SELECT macro_area,
       round(max(beds_per1000) FILTER (WHERE year = 2013), 2) AS y2013,
       round(max(beds_per1000) FILTER (WHERE year = 2023), 2) AS y2023,
       round(100 * (max(beds_per1000) FILTER (WHERE year = 2023)
                  / max(beds_per1000) FILTER (WHERE year = 2013) - 1), 1) AS pct_change
FROM macro
GROUP BY macro_area
ORDER BY pct_change;

-- A3. Within each region, the province with the most and fewest practising
-- specialists per 1,000 residents (latest year), using window functions.
WITH latest AS (SELECT max(year) AS year FROM province_rates WHERE phys_spec_per1000 IS NOT NULL),
ranked AS (
    SELECT region_name, province_name, phys_spec_per1000,
           rank() OVER (PARTITION BY region_name ORDER BY phys_spec_per1000 DESC) AS top,
           rank() OVER (PARTITION BY region_name ORDER BY phys_spec_per1000 ASC)  AS bottom,
           count(*) OVER (PARTITION BY region_name) AS n
    FROM province_rates JOIN latest USING (year)
    WHERE phys_spec_per1000 IS NOT NULL
)
SELECT * FROM (
SELECT region_name,
       max(province_name)     FILTER (WHERE top = 1)    AS highest,
       max(phys_spec_per1000) FILTER (WHERE top = 1)    AS highest_rate,
       max(province_name)     FILTER (WHERE bottom = 1) AS lowest,
       max(phys_spec_per1000) FILTER (WHERE bottom = 1) AS lowest_rate
FROM ranked
WHERE n > 1
GROUP BY region_name
) t
ORDER BY highest_rate / lowest_rate DESC;

-- A4. Province bed trend: three-year moving average and change since 2013.
SELECT province_name, region_name, year, beds_per1000,
       round(avg(beds_per1000) OVER (PARTITION BY province_code ORDER BY year
                                     ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS beds_per1000_ma3,
       round(beds_per1000 - first_value(beds_per1000) OVER (PARTITION BY province_code ORDER BY year), 2)
           AS change_since_2013
FROM province_rates
WHERE year BETWEEN 2013 AND 2023 AND province_name IN ('Roma', 'Milano', 'Napoli')
ORDER BY province_name, year;

-- A5. Nurses per hospital bed by region over time, a rough staffing ratio.
SELECT region_name,
       round(max(nurses_hosp / beds) FILTER (WHERE year = 2013), 2) AS y2013,
       round(max(nurses_hosp / beds) FILTER (WHERE year = 2018), 2) AS y2018,
       round(max(nurses_hosp / beds) FILTER (WHERE year = 2023), 2) AS y2023
FROM region_panel
GROUP BY region_name
ORDER BY y2023 DESC NULLS LAST;
