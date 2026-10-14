# IMD real-time rainfall verification — 13 October 2026

This is the original source-verification snapshot. The downloader, overlap comparator and candidate exporter were added on 14 October; current implementation and staging results are in [Prediction_Pipeline_Implementation_2026-10-14.md](Prediction_Pipeline_Implementation_2026-10-14.md). Source availability and product overlap remain unresolved; the older offline-only description below records the state of the original review.

The 2026 real-time source was **not promoted into the production dataset**. Only three daily probes were successfully downloaded and validated; no complete 2026 calendar month was available in this staging exercise. The verified 2025 annual archive remains the newest complete rainfall year used in this refresh.

IMD's [real-time rainfall page](https://imdpune.gov.in/cmpg/Realtimedata/Rainfall/Rain_Download.html) describes daily rainfall on a 0.25° grid and provides a date-specific POST form. The live HTML's 241×281 map-grid text is inside an inactive comment. Its [sample control file](https://imdpune.gov.in/cmpg/Realtimedata/Rainfall/dataddmmyyyy.php) specifies 135×129 grid cells, starting at longitude 66.5° and latitude 6.5°, with 0.25° steps and -999 as missing. This matches the geometry and binary record size of IMD's [annual rainfall documentation](https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html), which states daily rainfall is measured in millimetres and stored south to north with longitude varying fastest.

The real-time control is a generic example: it contains a 2019 DSET filename, a June 2006 TDEF, and the label `RFANOMALY`. Those strings cannot establish the downloaded observation date or prove equivalence to the annual product. The dated response filename was therefore checked independently. Nonnegative values and the shared grid are supporting evidence for daily rainfall, but historical overlap against the annual archive was not established because bounded requests for 1 January and 15 June 2025 repeatedly timed out.

| Downloaded source date | Binary bytes | Usable cells | Maximum grid value | Response filename |
| --- | ---: | ---: | ---: | --- |
| 2026-01-01 | 69,660 | 4,964 | 50.916115 | `rain_ind0.25_26_01_01.grd` |
| 2026-06-15 | 69,660 | 4,964 | 84.422859 | `rain_ind0.25_26_06_15.grd` |
| 2026-09-30 | 69,660 | 4,964 | 95.400002 | `rain_ind0.25_26_09_30.grd` |

Each successful probe passed endpoint/date/filename checks, exact little-endian float32 record size, source checksum, finite values and the -999-only negative sentinel. Probes and response metadata remain under `data/raw/updates/20261013/imd_realtime_probe/`. An HTTP availability probe returned a redirect page rather than rainfall, and was excluded by the binary checks. HTTPS availability was intermittent; a nine-month batch was deliberately not launched.

`data_ingestion/imd_realtime.py` now provides an offline date plan, strict staged-day validation, complete-calendar-month sums and grid-point conversion compatible with the existing annual rainfall processor. It performs no network requests and never writes production CSVs or the database. Real-time data is explicitly labelled provisional. Every day in a month must exist with matching provenance, and any cell missing one daily value stays missing in the monthly total; missing days are never treated as zero rainfall. The Jan–Sep 2026 plan requires **273 daily files / 19,017,180 bytes**, so the three probes are insufficient.

Run the offline plan with:

```powershell
.\venv\Scripts\python.exe -m data_ingestion.imd_realtime --start 2026-01 --end 2026-09
```

Once complete source downloads and identity are independently verified, validate a staged folder with `--validate-staged --staged-dir <folder>`. This command fails if any calendar day is missing. It does not ingest or promote the data.

Validation: **14 targeted tests passed**, covering future/current-month rejection, bounded date plans, exact response date and checksum, invalid daily values, missing-day rejection, missing-cell monthly sums, grid orientation and the default offline CLI.
