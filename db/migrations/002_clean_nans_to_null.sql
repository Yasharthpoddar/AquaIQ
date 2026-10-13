-- Migration 002: Clean text/IEEE NaNs to SQL NULL in features table (D6)
-- Converts any stored IEEE NaNs into proper SQL NULLs so standard IS NULL / IS NOT NULL semantics work.

BEGIN;

UPDATE features
SET gwl_current = NULL
WHERE gwl_current = 'NaN'::real OR gwl_current::text = 'NaN';

UPDATE features
SET gwl_lag_3mo = NULL
WHERE gwl_lag_3mo = 'NaN'::real OR gwl_lag_3mo::text = 'NaN';

UPDATE features
SET gwl_lag_6mo = NULL
WHERE gwl_lag_6mo = 'NaN'::real OR gwl_lag_6mo::text = 'NaN';

UPDATE features
SET rainfall_current = NULL
WHERE rainfall_current = 'NaN'::real OR rainfall_current::text = 'NaN';

UPDATE features
SET rainfall_3mo_avg = NULL
WHERE rainfall_3mo_avg = 'NaN'::real OR rainfall_3mo_avg::text = 'NaN';

UPDATE features
SET monsoon_deficit_pct = NULL
WHERE monsoon_deficit_pct = 'NaN'::real OR monsoon_deficit_pct::text = 'NaN';

UPDATE features
SET temperature = NULL
WHERE temperature = 'NaN'::real OR temperature::text = 'NaN';

UPDATE features
SET evapotranspiration = NULL
WHERE evapotranspiration = 'NaN'::real OR evapotranspiration::text = 'NaN';

UPDATE features
SET water_balance_proxy = NULL
WHERE water_balance_proxy = 'NaN'::real OR water_balance_proxy::text = 'NaN';

-- Add check constraint or index if needed
COMMIT;
