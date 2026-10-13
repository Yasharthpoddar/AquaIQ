"""Deterministic district assignments to usable gridded source cells."""
import geopandas as gpd
import pandas as pd

# Distances are measured in an India-centred projection, never in degrees.
DISTANCE_CRS = "+proj=aeqd +lat_0=22.5 +lon_0=80 +datum=WGS84 +units=m +no_defs"


def assign_grid_cells(points, districts):
    """Use internal cells, or exactly one nearest usable cell per missing polygon.

    Callers must omit unusable/ocean cells. Source lat/lon indices and point
    geometry survive the fallback. Equal distances use the lowest source index.
    """
    if points.crs is None or districts.crs is None:
        raise ValueError("Grid and district geometries require a CRS")
    ordering = [c for c in ("lat_idx", "lon_idx") if c in points]
    if not ordering:
        ordering = [c for c in ("latitude", "longitude") if c in points]
    points = points.sort_values(ordering).copy().reset_index(drop=True) if ordering else points.copy().reset_index(drop=True)
    points["_grid_index"] = range(len(points))
    districts = districts.copy().to_crs(points.crs)
    districts["_dist_key"] = districts["st_nm"].astype(str) + "___" + districts["district"].astype(str)
    if districts["_dist_key"].duplicated().any():
        # Multiple fragments belong to the same administrative district.
        districts = districts.dissolve(by="_dist_key", as_index=False)
    if points.empty:
        raise ValueError("No usable grid cells available")
    joined = gpd.sjoin(points, districts[["district", "st_nm", "_dist_key", "geometry"]],
                       how="inner", predicate="within").drop(columns="index_right")
    joined["spatial_method"] = "within"
    joined["distance_m"] = 0.0
    missing = districts[~districts["_dist_key"].isin(joined["_dist_key"])]
    if not missing.empty:
        representatives = missing.copy()
        representatives["geometry"] = representatives.geometry.representative_point()
        # Each district asks for its nearest cell, not each cell for a district.
        nearest = gpd.sjoin_nearest(
            representatives.to_crs(DISTANCE_CRS),
            points[["_grid_index", "geometry"]].to_crs(DISTANCE_CRS),
            how="left", distance_col="distance_m")
        nearest = nearest.sort_values(["_dist_key", "distance_m", "_grid_index"]).drop_duplicates("_dist_key")
        metadata = nearest[["_dist_key", "district", "st_nm", "_grid_index", "distance_m"]]
        fallback = points.merge(metadata, on="_grid_index", how="inner")
        fallback["spatial_method"] = "nearest_usable_cell"
        joined = gpd.GeoDataFrame(pd.concat([joined, fallback], ignore_index=True),
                                 geometry="geometry", crs=points.crs)
    return joined.sort_values(["_dist_key", "_grid_index"]).reset_index(drop=True)
