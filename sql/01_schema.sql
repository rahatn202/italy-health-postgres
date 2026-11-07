-- Italy health resources: schema
-- Source: Istat, Health for All - Italia (June 2026 release)

DROP SCHEMA IF EXISTS hfa CASCADE;
CREATE SCHEMA hfa;
SET search_path = hfa;

CREATE TABLE region (
    region_num   smallint PRIMARY KEY,           -- Istat region number 1-20
    region_name  text     NOT NULL UNIQUE,
    macro_area   text     NOT NULL
        CHECK (macro_area IN ('Nord-ovest', 'Nord-est', 'Centro', 'Sud', 'Isole'))
);

CREATE TABLE province (
    province_code text     PRIMARY KEY,          -- HFA unit code (region + province)
    province_name text     NOT NULL,
    region_num    smallint NOT NULL REFERENCES region
);

CREATE TABLE indicator (
    indicator_id smallint PRIMARY KEY,           -- HFA indicator code
    short_name   text NOT NULL UNIQUE,
    title_it     text NOT NULL,                  -- original Istat label
    title_en     text NOT NULL,
    unit         text NOT NULL,
    hfa_group    text NOT NULL
);

-- One row per geography x indicator x year. A value belongs to either a
-- province or a region, never both; missing values are simply absent rows.
CREATE TABLE observation (
    observation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    province_code  text     REFERENCES province,
    region_num     smallint REFERENCES region,
    indicator_id   smallint NOT NULL REFERENCES indicator,
    year           smallint NOT NULL CHECK (year BETWEEN 1980 AND 2030),
    value          numeric  NOT NULL CHECK (value >= 0),
    CHECK ((province_code IS NULL) <> (region_num IS NULL))
);

CREATE UNIQUE INDEX observation_province_uq
    ON observation (province_code, indicator_id, year) WHERE province_code IS NOT NULL;
CREATE UNIQUE INDEX observation_region_uq
    ON observation (region_num, indicator_id, year) WHERE region_num IS NOT NULL;
CREATE INDEX observation_indicator_year_idx ON observation (indicator_id, year);
