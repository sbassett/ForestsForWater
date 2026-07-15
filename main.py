import os
import shutil
import time
import geopandas as gpd
from src.cache import should_skip_step, record_step_metadata
from src.pipeline import (
    step_1_harmonize_data,
    step_2_raster_algebra,
    step_3_vector_intersection,
    step_4_priority_aggregation
)

# Workspace Paths
DATA_DIR = "C:/Users/Steve/Projects/ForestsForWater/data"
RAW_DIR = os.path.join(DATA_DIR, "raw")
INTERIM_DIR = os.path.join(DATA_DIR, "interim")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")

# Input files
GDB_PATH = os.path.join(RAW_DIR, "WUS_PublicWaterSources_ReleaseVersion2/WUS_PublicWaterSources_v2_0.gdb")
FIRESHEDS_GDB_PATH = os.path.join(RAW_DIR, "RDS-2020-0054-4/Data/Firesheds_CONUS.gdb")
P_PATH = os.path.join(RAW_DIR, "Normal_1991_2020_bioclim/Normal_1991_2020_MAP.tif")
ET_PATH = os.path.join(RAW_DIR, "Normal_1991_2020_bioclim/Normal_1991_2020_Eref.tif")
BPS_RASTER_PATH = os.path.join(RAW_DIR, "LF2020_BPS_CONUS/Tif/LF2020_BPS_CONUS.tif")
BPS_CSV_PATH = os.path.join(RAW_DIR, "LF2020_BPS_CONUS/CSV_Data/LF2020_BPS.csv")

# Interim and output files
ALIGNED_P_PATH = os.path.join(INTERIM_DIR, "aligned_p.tif")
ALIGNED_ET_PATH = os.path.join(INTERIM_DIR, "aligned_et.tif")
ALIGNED_VEG_MASK_PATH = os.path.join(INTERIM_DIR, "aligned_veg_mask.tif")
NET_WATER_YIELD_VOL_PATH = os.path.join(INTERIM_DIR, "net_water_yield_vol.tif")
DRY_FOREST_YIELD_VOL_PATH = os.path.join(INTERIM_DIR, "dry_forest_yield_vol.tif")
PRECOMPUTED_FRAGMENTS_PATH = os.path.join(INTERIM_DIR, "precomputed_fragments.geojson")  # Stores the firesheds table now
FIRESHED_PRIORITY_SCORES_PATH = os.path.join(OUTPUT_DIR, "fireshed_priority_scores.geojson")
CACHE_FILE = os.path.join(OUTPUT_DIR, "pipeline_metadata.json")

# Artifact destination path
ARTIFACT_DIR = "C:/Users/Steve/.gemini/antigravity/brain/60c55d20-38dc-43e1-8856-d2067ef18149"
ARTIFACT_CACHE_FILE = os.path.join(ARTIFACT_DIR, "pipeline_metadata.json")

def run_pipeline(w1: float = 0.5, w2: float = 0.5, majority_filter: bool = False, mode: str = "linear"):
    print("=================================================================")
    print("STARTING FIRESHED PRIORITY INDEX ANALYSIS PIPELINE")
    print("=================================================================")
    start_time = time.time()
    
    # -----------------------------------------------------------------
    # STEP 1: Data Harmonization Engine (BpS Dry Forest)
    # -----------------------------------------------------------------
    step1_inputs = [P_PATH, ET_PATH, BPS_RASTER_PATH, BPS_CSV_PATH, GDB_PATH]
    step1_outputs = [ALIGNED_P_PATH, ALIGNED_ET_PATH, ALIGNED_VEG_MASK_PATH]
    step1_params = {}
    
    if should_skip_step("Step_1_Harmonize", step1_inputs, step1_outputs, step_1_harmonize_data, step1_params, CACHE_FILE):
        print("[Step 1] Cached. Skipping execution.")
    else:
        step_1_harmonize_data(
            p_path=P_PATH,
            et_path=ET_PATH,
            bps_raster_path=BPS_RASTER_PATH,
            bps_csv_path=BPS_CSV_PATH,
            gdb_path=GDB_PATH,
            aligned_p_path=ALIGNED_P_PATH,
            aligned_et_path=ALIGNED_ET_PATH,
            aligned_veg_mask_path=ALIGNED_VEG_MASK_PATH
        )
        record_step_metadata("Step_1_Harmonize", step1_inputs, step1_outputs, step_1_harmonize_data, step1_params, CACHE_FILE)

    # -----------------------------------------------------------------
    # STEP 2: Volumetric Raster Algebra
    # -----------------------------------------------------------------
    step2_inputs = [ALIGNED_P_PATH, ALIGNED_ET_PATH, ALIGNED_VEG_MASK_PATH]
    step2_outputs = [NET_WATER_YIELD_VOL_PATH, DRY_FOREST_YIELD_VOL_PATH]
    step2_params = {}
    
    if should_skip_step("Step_2_Raster_Algebra", step2_inputs, step2_outputs, step_2_raster_algebra, step2_params, CACHE_FILE):
        print("[Step 2] Cached. Skipping execution.")
    else:
        step_2_raster_algebra(
            aligned_p_path=ALIGNED_P_PATH,
            aligned_et_path=ALIGNED_ET_PATH,
            aligned_veg_mask_path=ALIGNED_VEG_MASK_PATH,
            net_water_yield_vol_path=NET_WATER_YIELD_VOL_PATH,
            dry_forest_yield_vol_path=DRY_FOREST_YIELD_VOL_PATH
        )
        record_step_metadata("Step_2_Raster_Algebra", step2_inputs, step2_outputs, step_2_raster_algebra, step2_params, CACHE_FILE)

    # -----------------------------------------------------------------
    # STEP 3: Fireshed Zonal Analytics & Proportional Beneficiary Allocation
    # -----------------------------------------------------------------
    step3_inputs = [GDB_PATH, FIRESHEDS_GDB_PATH, ALIGNED_VEG_MASK_PATH, NET_WATER_YIELD_VOL_PATH]
    step3_outputs = [PRECOMPUTED_FRAGMENTS_PATH]
    step3_params = {}
    
    if should_skip_step("Step_3_Vector_Intersection", step3_inputs, step3_outputs, step_3_vector_intersection, step3_params, CACHE_FILE):
        print("[Step 3] Cached. Skipping execution.")
    else:
        step_3_vector_intersection(
            gdb_path=GDB_PATH,
            firesheds_gdb_path=FIRESHEDS_GDB_PATH,
            aligned_veg_mask_path=ALIGNED_VEG_MASK_PATH,
            net_water_yield_vol_path=NET_WATER_YIELD_VOL_PATH,
            precomputed_fragments_path=PRECOMPUTED_FRAGMENTS_PATH
        )
        record_step_metadata("Step_3_Vector_Intersection", step3_inputs, step3_outputs, step_3_vector_intersection, step3_params, CACHE_FILE)

    # -----------------------------------------------------------------
    # STEP 4: Fireshed-Level Scoring & Normalization (Dynamic)
    # -----------------------------------------------------------------
    step4_inputs = [PRECOMPUTED_FRAGMENTS_PATH]
    step4_outputs = [FIRESHED_PRIORITY_SCORES_PATH]
    step4_params = {
        "w1": w1,
        "w2": w2,
        "majority_filter": majority_filter,
        "mode": mode
    }
    
    if should_skip_step("Step_4_Aggregation", step4_inputs, step4_outputs, step_4_priority_aggregation, step4_params, CACHE_FILE):
        print("[Step 4] Cached. Skipping execution.")
    else:
        print("--- Step 4: Fireshed-Level Scoring & Normalization ---")
        scores_df = step_4_priority_aggregation(
            precomputed_fragments_path=PRECOMPUTED_FRAGMENTS_PATH,
            w1=w1,
            w2=w2,
            majority_filter=majority_filter,
            mode=mode
        )
        
        # Save output GeoJSON directly from scores_df
        os.makedirs(os.path.dirname(FIRESHED_PRIORITY_SCORES_PATH), exist_ok=True)
        print(f"Saving prioritized fireshed boundaries to {FIRESHED_PRIORITY_SCORES_PATH}...")
        
        cols_to_keep = [
            'Fireshed_ID', 'Fireshed_Name', 'Fireshed_Code', 'Fireshed_State', 'Priority_Score',
            'Fireshed_Water_Yield', 'Fireshed_DF_Percent', 'Total_Beneficiaries', 'geometry'
        ]
        scores_df[cols_to_keep].to_file(FIRESHED_PRIORITY_SCORES_PATH, driver='GeoJSON')
        
        record_step_metadata("Step_4_Aggregation", step4_inputs, step4_outputs, step_4_priority_aggregation, step4_params, CACHE_FILE)
        print("Step 4 complete.")

    # Copy cache file to artifact directory
    if os.path.exists(CACHE_FILE):
        shutil.copy2(CACHE_FILE, ARTIFACT_CACHE_FILE)
        print(f"Copied pipeline metadata to artifact path: {ARTIFACT_CACHE_FILE}")

    elapsed = time.time() - start_time
    print("=================================================================")
    print(f"PIPELINE RUN COMPLETE in {elapsed:.2f} seconds.")
    print("=================================================================")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the Fireshed Priority Index Pipeline")
    parser.add_argument("--w1", type=float, default=0.5, help="Weight for Hydro-Social Efficiency (PPD)")
    parser.add_argument("--w2", type=float, default=0.5, help="Weight for Forest Footprint (Pct_DF)")
    parser.add_argument("--majority", action="store_true", help="Filter for majority dry forest source watersheds (>50%)")
    parser.add_argument("--mode", type=str, default="linear", choices=["linear", "multiplicative"], help="Aggregation mode")
    
    args = parser.parse_args()
    run_pipeline(w1=args.w1, w2=args.w2, majority_filter=args.majority, mode=args.mode)
