"""
AquaIQ -- ERA5 Downloader (Yash, Week 1)
------------------------------------------
Downloads monthly-mean 2m temperature and potential evaporation from the
Copernicus Climate Data Store (CDS) for the India bounding box, 2002-2024.
These become features 7 and 8 of the 10-feature list (temperature,
evapotranspiration) after district-level aggregation in era5_to_district.py.

ONE-TIME SETUP (do this before running):
1. Create a free account at https://cds.climate.copernicus.eu
2. Log in, go to your profile page, copy your Personal Access Token.
3. Create a file at ~/.cdsapirc (Windows: C:\\Users\\<you>\\.cdsapirc) containing:
       url: https://cds.climate.copernicus.eu/api
       key: <PASTE_YOUR_TOKEN_HERE>
4. Open this dataset's page in a browser ONCE and click "Download data",
   accepting the Terms of Use when prompted. The API returns 403 until you
   do this manually, even with a valid key -- this is the #1 thing that
   trips people up.
       https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-monthly-means
5. pip install cdsapi (already in requirements.txt)

Then just run: python download_era5.py
"""

import os
import cdsapi

OUTPUT_DIR = "data/raw/era5"
os.makedirs(OUTPUT_DIR, exist_ok=True)

client = cdsapi.Client()

# India bounding box: [North, West, South, East]
INDIA_AREA = [38, 68, 6, 98]

YEARS = [str(y) for y in range(2002, 2025)]
MONTHS = [f"{m:02d}" for m in range(1, 13)]

DATASET = "reanalysis-era5-single-levels-monthly-means"

REQUEST = {
    "product_type": ["monthly_averaged_reanalysis"],
    "variable": [
        "2m_temperature",
        "potential_evaporation",
    ],
    "year": YEARS,
    "month": MONTHS,
    "time": ["00:00"],   # monthly means only need one timestamp per month
    "area": INDIA_AREA,
    "data_format": "netcdf",
}

TARGET = os.path.join(OUTPUT_DIR, "era5_temp_pet_india_2002_2024.nc")

if __name__ == "__main__":
    print(f"Requesting ERA5 monthly means for {YEARS[0]}-{YEARS[-1]} over India...")
    print("This queues on ECMWF's servers -- for a request this size, expect")
    print("anywhere from a few minutes to a couple hours depending on load.")
    print("The script blocks and downloads automatically once it's ready.\n")

    client.retrieve(DATASET, REQUEST, TARGET)

    print(f"\nDone. Saved to {TARGET}")
    print()
    print("IMPORTANT -- sign convention gotcha for potential_evaporation:")
    print("ERA5 reports evaporation as NEGATIVE (downward-flux convention),")
    print("in metres of water equivalent. When building water_balance_proxy")
    print("(feature 9: rainfall - ET) in Week 4, convert first:")
    print("    pet_mm = pet_raw * -1000   # m (negative) -> mm (positive)")
