import os
import numpy as np
import geopandas as gpd
import pandas as pd
import rasterio
import rasterio.warp
import rasterio.features
from rasterio.transform import from_origin
from rasterio.mask import mask
import shapely
import shapely.geometry
import shapely.ops
from typing import Dict, Any, List

# Target Equal-Area CRS
TARGET_CRS = "EPSG:5070"  # NAD83 / Conus Albers

def get_target_grid_template(gdb_path: str):
    """
    Reads the DiversionSource layer from the geodatabase, reprojects it to EPSG:5070,
    and returns the 1km resolution template grid extent, transform, shape.
    """
    print("Computing target grid template from public water sources...")
    ds_gdf = gpd.read_file(gdb_path, layer='DiversionSource')
    ds_gdf_5070 = ds_gdf.to_crs(TARGET_CRS)
    minx, miny, maxx, maxy = ds_gdf_5070.total_bounds
    
    # Align bounds to 1km grid (multiples of 1000m)
    minx = np.floor(minx / 1000.0) * 1000.0
    miny = np.floor(miny / 1000.0) * 1000.0
    maxx = np.ceil(maxx / 1000.0) * 1000.0
    maxy = np.ceil(maxy / 1000.0) * 1000.0
    
    width = int((maxx - minx) / 1000.0)
    height = int((maxy - miny) / 1000.0)
    transform = from_origin(minx, maxy, 1000.0, 1000.0)
    
    print(f"Target Grid: {width} x {height} pixels, Bounds: [{minx}, {miny}, {maxx}, {maxy}]")
    return transform, width, height, minx, miny, maxx, maxy

def step_1_harmonize_data(
    p_path: str,
    et_path: str,
    bps_raster_path: str,
    bps_csv_path: str,
    gdb_path: str,
    aligned_p_path: str,
    aligned_et_path: str,
    aligned_veg_mask_path: str
):
    """
    Step 1: Harmonization Engine (LANDFIRE BpS Edition)
    - Reproject and align P and ET rasters to 1km EPSG:5070.
    - Identify dry conifer and oak-conifer settings in the Western US from BpS attributes.
    - Reclassify BpS raster to a binary mask (1 = Dry Forest, 0 = Other).
    """
    print("--- Step 1: Harmonization Engine (BpS Dry Forest) ---")
    transform, width, height, minx, miny, maxx, maxy = get_target_grid_template(gdb_path)
    
    os.makedirs(os.path.dirname(aligned_p_path), exist_ok=True)
    
    # 1. Reproject and align P raster (Precipitation)
    print(f"Reprojecting and aligning Precipitation from {p_path}...")
    with rasterio.open(p_path) as src:
        p_aligned = np.zeros((height, width), dtype=np.float32)
        rasterio.warp.reproject(
            source=rasterio.band(src, 1),
            destination=p_aligned,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=transform,
            dst_crs=TARGET_CRS,
            dst_nodata=np.nan,
            resampling=rasterio.warp.Resampling.bilinear
        )
        
    # 2. Reproject and align ET raster (Evapotranspiration)
    print(f"Reprojecting and aligning Evapotranspiration from {et_path}...")
    with rasterio.open(et_path) as src:
        et_aligned = np.zeros((height, width), dtype=np.float32)
        rasterio.warp.reproject(
            source=rasterio.band(src, 1),
            destination=et_aligned,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=transform,
            dst_crs=TARGET_CRS,
            dst_nodata=np.nan,
            resampling=rasterio.warp.Resampling.bilinear
        )
        
    # 3. Read BpS CSV and identify dry forest values
    print(f"Reading BpS mapping table from {bps_csv_path}...")
    bps_df = pd.read_csv(bps_csv_path)
    keywords = ["ponderosa", "jeffrey", "oak-ponderosa", "dry conifer"]
    
    def check_dry_forest(row):
        name_lower = str(row['BPS_NAME']).lower()
        matches_primary = any(kw in name_lower for kw in keywords)
        is_dry_mesic_conifer = "dry-mesic" in name_lower and ("conifer" in name_lower or "mixed conifer" in name_lower or "forest" in name_lower or "woodland" in name_lower or "savanna" in name_lower)
        is_chaparral_or_desert = "chaparral" in name_lower or "desert" in name_lower or "scrub" in name_lower
        return (matches_primary or is_dry_mesic_conifer) and not is_chaparral_or_desert

    bps_df['Is_Dry_Forest'] = bps_df.apply(check_dry_forest, axis=1)
    dry_forest_values = set(bps_df[bps_df['Is_Dry_Forest']]['VALUE'].tolist())
    print(f"Found {len(dry_forest_values)} BpS classes classified as dry forest.")

    # 4. Reproject and align BpS raster
    print(f"Reprojecting and aligning BpS raster from {bps_raster_path}...")
    with rasterio.open(bps_raster_path) as src:
        bps_aligned = np.zeros((height, width), dtype=np.int16)
        rasterio.warp.reproject(
            source=rasterio.band(src, 1),
            destination=bps_aligned,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=transform,
            dst_crs=TARGET_CRS,
            dst_nodata=32767,
            resampling=rasterio.warp.Resampling.nearest
        )
        
    # Reclassify aligned BpS codes to binary dry forest mask
    print("Reclassifying BpS to binary dry forest mask (1 = Dry Forest)...")
    veg_mask = np.isin(bps_aligned, list(dry_forest_values)).astype(np.uint8)
    
    # Write aligned rasters
    meta = {
        'driver': 'GTiff',
        'dtype': 'float32',
        'nodata': np.nan,
        'width': width,
        'height': height,
        'count': 1,
        'crs': TARGET_CRS,
        'transform': transform
    }
    
    with rasterio.open(aligned_p_path, 'w', **meta) as dst:
        dst.write(p_aligned, 1)
        
    with rasterio.open(aligned_et_path, 'w', **meta) as dst:
        dst.write(et_aligned, 1)
        
    # Write vegetation mask as uint8
    veg_meta = meta.copy()
    veg_meta['dtype'] = 'uint8'
    veg_meta['nodata'] = 0
    with rasterio.open(aligned_veg_mask_path, 'w', **veg_meta) as dst:
        dst.write(veg_mask, 1)
        
    print("Step 1 complete.")

def step_2_raster_algebra(
    aligned_p_path: str,
    aligned_et_path: str,
    aligned_veg_mask_path: str,
    net_water_yield_vol_path: str,
    dry_forest_yield_vol_path: str
):
    """
    Step 2: Volumetric Raster Algebra
    - Yield (mm) = Max(0, P - ET)
    - Dry Forest Yield (mm) = Yield * Dry Forest Mask
    - Convert cell linear depth (mm) to spatial volume (m³):
      Volume = Depth_mm * 1000.0 (since cell area is 1,000,000 m²)
    """
    print("--- Step 2: Volumetric Raster Algebra ---")
    with rasterio.open(aligned_p_path) as src_p, \
         rasterio.open(aligned_et_path) as src_et, \
         rasterio.open(aligned_veg_mask_path) as src_veg:
        
        p = src_p.read(1)
        et = src_et.read(1)
        veg = src_veg.read(1)
        meta = src_p.meta.copy()
        
    # Replace nan with 0 for subtraction safely
    p_clean = np.nan_to_num(p, nan=0.0)
    et_clean = np.nan_to_num(et, nan=0.0)
    
    # Calculate yield (mm)
    yield_mm = np.maximum(0.0, p_clean - et_clean)
    
    # Convert mm to m3 volume (Depth_mm / 1000 * 1,000,000 = Depth_mm * 1000)
    net_yield_vol = yield_mm * 1000.0
    
    # Isolate dry forest yield volume
    df_yield_vol = net_yield_vol * veg
    
    # Save rasters
    with rasterio.open(net_water_yield_vol_path, 'w', **meta) as dst:
        dst.write(net_yield_vol.astype(np.float32), 1)
        
    with rasterio.open(dry_forest_yield_vol_path, 'w', **meta) as dst:
        dst.write(df_yield_vol.astype(np.float32), 1)
        
    print("Step 2 complete.")

def build_system_dependency_graph(conn_df: pd.DataFrame) -> Dict[str, set]:
    """Builds an adjacency list representing System dependencies (Destination -> upstream Sources)."""
    graph = {}
    for _, row in conn_df.iterrows():
        src = str(row['SourceWSID']).strip()
        dest = str(row['DestinationWSID']).strip()
        if src and dest and src != 'nan' and dest != 'nan':
            if dest not in graph:
                graph[dest] = set()
            graph[dest].add(src)
    return graph

def get_all_upstream_wsids(target_wsid: str, graph: Dict[str, set]) -> set:
    """Traverses the dependency graph backwards to find all upstream WSIDs a system depends on."""
    visited = set()
    queue = [target_wsid]
    visited.add(target_wsid)
    while queue:
        curr = queue.pop(0)
        for parent in graph.get(curr, []):
            if parent not in visited:
                visited.add(parent)
                queue.append(parent)
    return visited

def get_raster_sum_for_polygons(raster_path: str, geometries: List[shapely.geometry.base.BaseGeometry]) -> List[float]:
    """Calculates the sum of raster values inside each geometry using rasterio.mask."""
    sums = []
    with rasterio.open(raster_path) as src:
        for i, geom in enumerate(geometries):
            if geom.is_empty:
                sums.append(0.0)
                continue
            try:
                # Mask raster with the polygon
                out_image, _ = mask(src, [geom], crop=True, nodata=0.0)
                band = out_image[0]
                band_clean = np.nan_to_num(band, nan=0.0)
                sums.append(float(band_clean.sum()))
            except Exception as e:
                # Occurs if geometry is outside the raster bounds
                sums.append(0.0)
    return sums

def step_3_vector_intersection(
    gdb_path: str,
    firesheds_gdb_path: str,
    aligned_veg_mask_path: str,
    net_water_yield_vol_path: str,
    precomputed_fragments_path: str  # Retained path name for backward compatibility; represents firesheds_filtered.geojson
):
    """
    Step 3: Fireshed Zonal Analytics & Proportional Beneficiary Allocation
    - Resolves water system dependencies and constructs True Source Areas for municipal watersheds.
    - Projects all geometries to TARGET_CRS (EPSG:5070) and clips to Western US study bounds.
    - Performs zonal statistics on net water yield volume and dry forest mask directly on firesheds.
    - Allocates population served (beneficiaries) to fireshed boundaries using area-weighted overlay.
    - Saves the lightweight, attribute-rich firesheds GeoJSON.
    """
    print("--- Step 3: Fireshed Zonal Analytics & Beneficiary Allocation ---")
    
    # 1. Load Geodatabase Layers
    print("Loading Public Water Source layers from GDB...")
    sys_df = gpd.read_file(gdb_path, layer='System')
    ds_gdf = gpd.read_file(gdb_path, layer='DiversionSource')
    conn_df = gpd.read_file(gdb_path, layer='SystemConnection')
    
    print("Loading Fireshed Registry layer...")
    firesheds_gdf = gpd.read_file(firesheds_gdb_path, layer='Firesheds')
    
    # 2. Build dependency graph & find upstream systems
    print("Resolving upstream system dependencies...")
    graph = build_system_dependency_graph(conn_df)
    
    # Filter systems with population > 0
    active_sys_df = sys_df[sys_df['POPULATION_SERVED_COUNT'] > 0].dropna(subset=['WSID'])
    print(f"Found {len(active_sys_df)} water systems with population > 0.")
    
    # Dissolve DiversionSource geometries by WSID to optimize unioning
    print("Dissolving raw diversion sources by WSID...")
    ds_dissolved = ds_gdf.dissolve(by='WSID')
    wsid_to_geom = ds_dissolved['geometry'].to_dict()
    
    # Construct True Source Area for each system
    print("Constructing True Source Area polygons...")
    true_source_records = []
    union_cache = {}
    
    for _, row in active_sys_df.iterrows():
        wsid = str(row['WSID']).strip()
        pop = float(row['POPULATION_SERVED_COUNT'])
        
        upstream_wsids = get_all_upstream_wsids(wsid, graph)
        geoms_wsids = sorted([sid for sid in upstream_wsids if sid in wsid_to_geom])
        if not geoms_wsids:
            continue
            
        geom_key = tuple(geoms_wsids)
        if geom_key in union_cache:
            true_source_geom = union_cache[geom_key]
        else:
            if len(geoms_wsids) == 1:
                true_source_geom = wsid_to_geom[geoms_wsids[0]]
            else:
                geoms = [wsid_to_geom[sid] for sid in geoms_wsids]
                true_source_geom = shapely.ops.unary_union(geoms)
            union_cache[geom_key] = true_source_geom
            
        if true_source_geom.is_empty:
            continue
            
        true_source_records.append({
            'watershed_id': wsid,
            'population_served': pop,
            'geometry': true_source_geom
        })
        
    watersheds_gdf = gpd.GeoDataFrame(true_source_records, crs=ds_gdf.crs)
    print(f"Created True Source Area layer for {len(watersheds_gdf)} water systems.")
    
    # Reproject to TARGET_CRS
    print("Reprojecting True Source Areas and Firesheds to EPSG:5070...")
    watersheds_gdf = watersheds_gdf.to_crs(TARGET_CRS)
    firesheds_gdf = firesheds_gdf.to_crs(TARGET_CRS)
    
    # Filter firesheds to the Western US study bounds based on watershed bounds
    minx, miny, maxx, maxy = watersheds_gdf.total_bounds
    firesheds_filtered = firesheds_gdf.cx[minx:maxx, miny:maxy].copy()
    print(f"Filtered firesheds count: {len(firesheds_filtered)} (out of {len(firesheds_gdf)})")
    
    # Calculate Water Yield Zonal Sum
    print("Calculating raw water yield volume for each fireshed boundary...")
    firesheds_filtered['Fireshed_Water_Yield'] = get_raster_sum_for_polygons(net_water_yield_vol_path, firesheds_filtered.geometry)
    
    # Calculate Dry Forest Percent Zonal Sum
    print("Calculating dry forest percentage for each fireshed boundary...")
    # Each pixel in aligned_veg_mask is 1 km2 = 1,000,000 m2. Sum of pixels * 1e6 is dry forest area in m2.
    pixel_sums = get_raster_sum_for_polygons(aligned_veg_mask_path, firesheds_filtered.geometry)
    firesheds_filtered['Fireshed_DF_Percent'] = np.where(
        firesheds_filtered.geometry.area > 0.0,
        ((np.array(pixel_sums) * 1e6) / firesheds_filtered.geometry.area) * 100.0,
        0.0
    )
    firesheds_filtered['Fireshed_DF_Percent'] = firesheds_filtered['Fireshed_DF_Percent'].clip(0.0, 100.0)
    
    # Area-weighted proportional population served (beneficiaries) for each fireshed
    print("Calculating area-weighted proportional beneficiaries for each fireshed...")
    watersheds_gdf['ws_area_m2'] = watersheds_gdf.geometry.area
    
    # Simplify geometries to speed up overlay
    print("Simplifying geometries for spatial overlay (tolerance = 100m)...")
    watersheds_gdf['geometry'] = watersheds_gdf.geometry.simplify(100.0, preserve_topology=True).make_valid()
    firesheds_filtered['geometry'] = firesheds_filtered.geometry.simplify(100.0, preserve_topology=True).make_valid()
    
    intersections = gpd.overlay(firesheds_filtered, watersheds_gdf, how='intersection')
    intersections['intersect_area_m2'] = intersections.geometry.area
    intersections['prop_population'] = np.where(
        intersections['ws_area_m2'] > 0.0,
        (intersections['intersect_area_m2'] / intersections['ws_area_m2']) * intersections['population_served'],
        0.0
    )
    
    fireshed_pop = intersections.groupby('Fireshed_ID')['prop_population'].sum().reset_index().rename(columns={'prop_population': 'Total_Beneficiaries'})
    
    # Merge beneficiaries back to firesheds
    firesheds_filtered = firesheds_filtered.merge(fireshed_pop, on='Fireshed_ID', how='left')
    firesheds_filtered['Total_Beneficiaries'] = firesheds_filtered['Total_Beneficiaries'].fillna(0.0)
    
    # Save the filtered firesheds with attributes to the precomputed fragments path
    print(f"Saving filtered fireshed boundaries with attributes to {precomputed_fragments_path}...")
    os.makedirs(os.path.dirname(precomputed_fragments_path), exist_ok=True)
    
    cols_to_keep = [
        'Fireshed_ID', 'Fireshed_Name', 'Fireshed_Code', 'Fireshed_State',
        'Fireshed_Water_Yield', 'Fireshed_DF_Percent', 'Total_Beneficiaries', 'geometry'
    ]
    firesheds_filtered[cols_to_keep].to_file(precomputed_fragments_path, driver='GeoJSON')
    
    # Copy file to data/interim/firesheds_filtered.geojson for consistency
    filtered_path = os.path.join(os.path.dirname(precomputed_fragments_path), "firesheds_filtered.geojson")
    if os.path.abspath(precomputed_fragments_path) != os.path.abspath(filtered_path):
        firesheds_filtered[cols_to_keep].to_file(filtered_path, driver='GeoJSON')
        
    print("Step 3 complete.")

def step_4_priority_aggregation(
    precomputed_fragments_path: Any,  # Retained path name for backward compatibility; represents firesheds GeoJSON file
    w1: float,
    w2: float,
    majority_filter: bool,
    mode: str = "linear",
    people_inclusion_mode: str = "ppd"
) -> gpd.GeoDataFrame:
    """
    Step 4: Fireshed-Level Scoring & Normalization (Dynamic)
    - Computes dynamic linear/multiplicative priority scores on the fireshed boundaries table in memory.
    - Applies majority dry forest filter and min-max normalization to [0.0, 1.0].
    """
    print("--- Step 4: Fireshed-Level Scoring & Normalization ---")
    if isinstance(precomputed_fragments_path, str):
        df = gpd.read_file(precomputed_fragments_path)
    else:
        df = precomputed_fragments_path.copy()

    if len(df) == 0:
        return gpd.GeoDataFrame(columns=['Fireshed_ID', 'Priority_Score', 'geometry'])

    # Populate standard naming for backward compatibility
    df['Water_Yield_Vol'] = df['Fireshed_Water_Yield'].fillna(0.0)
    df['Dry_Forest_Percent'] = df['Fireshed_DF_Percent'].fillna(0.0)
    df['Total_Beneficiaries'] = df['Total_Beneficiaries'].fillna(0.0)

    # Compute People-Per-Drop (PPD)
    df['People_Per_Drop'] = np.where(
        df['Water_Yield_Vol'] > 0.0,
        df['Total_Beneficiaries'] / df['Water_Yield_Vol'],
        0.0
    )

    # Choose how people are included in the model: "ppd", "beneficiaries", or "none" (ecological/hydrological only)
    if people_inclusion_mode == "beneficiaries":
        df['People_Metric'] = df['Total_Beneficiaries']
    elif people_inclusion_mode == "none":
        df['People_Metric'] = df['Water_Yield_Vol']
    else:  # "ppd" (default)
        df['People_Metric'] = df['People_Per_Drop']

    # Compute Priority Score
    if mode == "multiplicative":
        df['Fragment_Score_ij'] = df['People_Metric'] * df['Dry_Forest_Percent']
    else:  # linear
        # Min-max normalize components across all active firesheds
        min_metric = df['People_Metric'].min()
        max_metric = df['People_Metric'].max()
        min_forest = df['Dry_Forest_Percent'].min()
        max_forest = df['Dry_Forest_Percent'].max()
        
        norm_metric = (df['People_Metric'] - min_metric) / (max_metric - min_metric) if max_metric > min_metric else df['People_Metric'] * 0.0
        norm_forest = (df['Dry_Forest_Percent'] - min_forest) / (max_forest - min_forest) if max_forest > min_forest else df['Dry_Forest_Percent'] * 0.0
        
        # Apply weights and geometric penalty if people_inclusion_mode == "none"
        if people_inclusion_mode == "none":
            df['Fragment_Score_ij'] = (w1 * norm_metric + w2 * norm_forest) * norm_metric * norm_forest
        else:
            df['Fragment_Score_ij'] = w1 * norm_metric + w2 * norm_forest

    # Filter by Majority Dry Forest if requested (at least 50.0% dry forest)
    if majority_filter:
        df['Fragment_Score_ij'] = np.where(df['Dry_Forest_Percent'] >= 50.0, df['Fragment_Score_ij'], 0.0)

    # Normalize Priority_Score between 0.0 and 1.0
    min_score = df['Fragment_Score_ij'].min()
    max_score = df['Fragment_Score_ij'].max()
    if max_score > min_score:
        df['Priority_Score'] = (df['Fragment_Score_ij'] - min_score) / (max_score - min_score)
    else:
        df['Priority_Score'] = 0.0

    return df
