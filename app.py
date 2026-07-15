import os
import streamlit as st
import geopandas as gpd
import numpy as np
import folium
from streamlit_folium import st_folium
import branca.colormap as cm
from typing import Any
from src.pipeline import step_4_priority_aggregation

# Page Configuration
st.set_page_config(
    page_title="Fireshed Priority Index Dashboard",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Workspace Paths
DATA_DIR = "C:/Users/Steve/Projects/ForestsForWater/data"
INTERIM_DIR = os.path.join(DATA_DIR, "interim")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PRECOMPUTED_FRAGMENTS_PATH = os.path.join(INTERIM_DIR, "precomputed_fragments.geojson")
FIRESHEDS_GDB_PATH = os.path.join(RAW_DIR, "RDS-2020-0054-4/Data/Firesheds_CONUS.gdb")
FIRESHED_PRIORITY_SCORES_PATH = os.path.join(DATA_DIR, "output/fireshed_priority_scores.geojson")

# Custom CSS for Premium Aesthetics
st.markdown("""
    <style>
        .main {
            background-color: #f8f9fa;
        }
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        h1 {
            color: #1e3d59;
            font-family: 'Outfit', 'Inter', sans-serif;
            font-weight: 700;
            margin-bottom: 0.2rem;
        }
        .subtitle {
            color: #17b978;
            font-size: 1.2rem;
            font-weight: 500;
            margin-bottom: 2rem;
        }
        .metric-card {
            background: white;
            padding: 1.2rem;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
            border-left: 5px solid #17b978;
            margin-bottom: 1rem;
        }
        .metric-title {
            font-size: 0.9rem;
            color: #6c757d;
            text-transform: uppercase;
            font-weight: 600;
            margin-bottom: 0.3rem;
        }
        .metric-value {
            font-size: 1.8rem;
            color: #1e3d59;
            font-weight: 700;
        }
        .control-panel {
            background-color: #ffffff;
            padding: 2rem;
            border-radius: 16px;
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.06);
        }
        .stButton>button {
            background-color: #1e3d59;
            color: white;
            border-radius: 8px;
            font-weight: 600;
        }
        .stButton>button:hover {
            background-color: #17b978;
            color: white;
        }
    </style>
""", unsafe_allow_html=True)

st.write("<h1>Fireshed Priority Index (FPI) Dashboard</h1>", unsafe_allow_html=True)
st.write("<div class='subtitle'>Multi-Scale Geospatial Analysis Coupling Climate & Municipal Watershed Vectors</div>", unsafe_allow_html=True)

# Cache data loading to prevent disk reads on user input
@st.cache_data
def load_cached_data(display_mtime):
    if not os.path.exists(FIRESHED_PRIORITY_SCORES_PATH):
        return None
    
    # Load display fireshed geometries (already simplified and merged in main.py)
    firesheds_display = gpd.read_file(FIRESHED_PRIORITY_SCORES_PATH)
    
    # Convert to WGS84 (EPSG:4326) for Folium
    firesheds_display = firesheds_display.to_crs(epsg=4326)
    
    return firesheds_display

display_mtime = os.path.getmtime(FIRESHED_PRIORITY_SCORES_PATH) if os.path.exists(FIRESHED_PRIORITY_SCORES_PATH) else 0.0
firesheds_display = load_cached_data(display_mtime)

if firesheds_display is None:
    st.error("⚠️ Prioritized fireshed boundaries not found. Please run the pipeline (`python main.py`) first to generate them.")
    st.stop()

# Layout: Left column for controls, Right column for map
col_left, col_right = st.columns([1, 2], gap="large")

with col_left:
    st.markdown("<div class='control-panel'>", unsafe_allow_html=True)
    st.markdown("### ⚙️ Calibration Model Controls")
    
    # Social Metric Mode selection
    st.markdown("**Social Weighting / Ecological Mode:**")
    people_inclusion_mode = st.radio(
        "Weighting Target:",
        options=[
            "People-Per-Drop (PPD)",
            "Total Beneficiaries (Absolute Population)",
            "None (Ecological & Hydrological Runoff Only)"
        ],
        index=0,
        help="Select whether to factor in population served (PPD or Beneficiaries) or exclude human population to focus purely on water yield and dry forests.",
        horizontal=False
    )
    if people_inclusion_mode.startswith("People-Per-Drop"):
        people_mode_code = "ppd"
    elif people_inclusion_mode.startswith("Total Beneficiaries"):
        people_mode_code = "beneficiaries"
    else:
        people_mode_code = "none"

    st.write("---")
    
    # Format formula label dynamically based on mode
    if people_mode_code == "ppd":
        mult_label = "Multiplicative Joint Index (PPD * Pct_DF)"
    elif people_mode_code == "beneficiaries":
        mult_label = "Multiplicative Joint Index (Pop * Pct_DF)"
    else:
        mult_label = "Multiplicative Joint Index (Yield * Pct_DF)"

    # Mode selection
    mode = st.radio(
        "Priority Index Formula:",
        options=["linear", "multiplicative"],
        format_func=lambda x: "Weighted Linear Index" if x == "linear" else mult_label,
        help="Select the mathematical aggregation formula for Step 4."
    )
    
    w1, w2 = 0.5, 0.5
    if mode == "linear":
        st.write("---")
        st.markdown("**Adjust Weights (must sum to 1.0):**")
        if people_mode_code == "ppd":
            w1_label = "💧 Hydro-Social Efficiency Weight (w1):"
        elif people_mode_code == "beneficiaries":
            w1_label = "👥 Total Beneficiaries Weight (w1):"
        else:
            w1_label = "💧 Hydrological Yield Weight (w1):"
            
        w1 = st.slider(
            w1_label,
            min_value=0.0,
            max_value=1.0,
            value=0.5,
            step=0.05,
            help="Weight assigned to the water yield/social priority metric."
        )
        w2 = 1.0 - w1
        st.info(f"🌿 Forest Footprint Weight (w2): **{w2:.2f}**")
    
    st.write("---")
    majority_filter = st.checkbox(
        "Filter for 'Majority Dry Forest' source watersheds",
        value=False,
        help="Only include fragments originating from watersheds where Dry Forest coverage exceeds 50.0%."
    )
    
    st.write("---")
    min_df_threshold = st.slider(
        "Min Dry Forest Cover Threshold (%):",
        min_value=0.0,
        max_value=50.0,
        value=10.0,
        step=1.0,
        help="Firesheds with overall dry forest cover below this percentage will have their priority scores set to 0.0."
    )
    
    st.write("---")
    st.markdown("**Map Symbology Settings:**")
    symbology_mode = st.selectbox(
        "Color Symbology Style:",
        options=["Continuous Scale", "Quantile Classes (Discrete)"],
        index=1,
        help="Choose how the fireshed priority scores are classified on the map."
    )
    
    st.write("---")
    st.markdown("**Map Layer Settings:**")
    map_layer = st.selectbox(
        "Select Map Layer to Visualize:",
        options=[
            "Fireshed Priority Score",
            "Total Beneficiaries (People)",
            "Dry Forest Coverage %",
            "Water Yield Volume (m3)",
            "People-Per-Drop (Efficiency)"
        ],
        index=0,
        help="Select which calculated metric to visualize on the map."
    )
    
    LAYER_MAP = {
        "Fireshed Priority Score": "Priority_Score",
        "Total Beneficiaries (People)": "Total_Beneficiaries",
        "Dry Forest Coverage %": "Dry_Forest_Percent",
        "Water Yield Volume (m3)": "Water_Yield_Vol",
        "People-Per-Drop (Efficiency)": "People_Per_Drop"
    }
    col_name = LAYER_MAP[map_layer]
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Dynamic calculations (in-memory, extremely fast)
    with st.spinner("Recalculating Fireshed Priority scores..."):
        # Pass firesheds_display directly to calculate scores in memory in under a millisecond
        map_gdf = step_4_priority_aggregation(
            precomputed_fragments_path=firesheds_display,
            w1=w1,
            w2=w2,
            majority_filter=majority_filter,
            mode=mode,
            people_inclusion_mode=people_mode_code
        )
        
        # Populate standard visualizer naming
        map_gdf['Water_Yield_Vol'] = map_gdf['Fireshed_Water_Yield'].fillna(0.0)
        map_gdf['Dry_Forest_Percent'] = map_gdf['Fireshed_DF_Percent'].fillna(0.0)
        map_gdf['Total_Beneficiaries'] = map_gdf['Total_Beneficiaries'].fillna(0.0)
        
        # Apply the dry forest threshold filter
        # Firesheds with overall Dry Forest cover below min_df_threshold get a Priority_Score of 0.0
        map_gdf['Priority_Score'] = np.where(map_gdf['Dry_Forest_Percent'] >= min_df_threshold, map_gdf['Priority_Score'], 0.0)

        
    st.markdown("### 📊 Summary Statistics")
    
    # Show key metrics
    num_prioritized = len(map_gdf[map_gdf['Priority_Score'] > 0])
    mean_score = map_gdf['Priority_Score'].mean() if len(map_gdf) > 0 else 0.0
    
    st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-title'>Active Prioritized Firesheds</div>
            <div class='metric-value'>{num_prioritized}</div>
        </div>
        <div class='metric-card' style='border-left-color: #1e3d59;'>
            <div class='metric-title'>Mean Priority Score</div>
            <div class='metric-value'>{mean_score:.3f}</div>
        </div>
    """, unsafe_allow_html=True)
    
    # Dynamic Quantile Legend
    if symbology_mode == "Quantile Classes (Discrete)" and len(map_gdf) > 0:
        # Filter for active scores (> 0.0) for quantile threshold calculations
        active_scores = map_gdf.loc[map_gdf[col_name] > 0.0, col_name]
        if len(active_scores) > 0:
            q50 = active_scores.quantile(0.50)
            q75 = active_scores.quantile(0.75)
            q90 = active_scores.quantile(0.90)
        else:
            q50, q75, q90 = 0.1, 0.25, 0.5
            
        unit_str = ""
        if col_name == "Water_Yield_Vol":
            unit_str = " m³"
        elif col_name == "Dry_Forest_Percent":
            unit_str = "%"
            
        fmt = lambda x: f"{x:.3f}" if col_name == "Priority_Score" else (f"{x:.5f}" if col_name == "People_Per_Drop" else (f"{x:,.0f}" if col_name == "Total_Beneficiaries" else f"{x:.1f}"))
        
        st.markdown(f"""
            <div style='background: white; padding: 1rem; border-radius: 8px; border: 1px solid #ddd; margin-top: 1rem; margin-bottom: 1rem;'>
                <div style='font-weight: bold; margin-bottom: 0.5rem; color: #1e3d59;'>Quantile Legend ({map_layer})</div>
                <div style='display: flex; align-items: center; margin-bottom: 0.4rem;'>
                    <span style='display: inline-block; width: 16px; height: 16px; background-color: #d73027; margin-right: 0.6rem; border-radius: 4px;'></span>
                    <span>🔴 <strong>Top 10%</strong> (&ge; {fmt(q90)}{unit_str})</span>
                </div>
                <div style='display: flex; align-items: center; margin-bottom: 0.4rem;'>
                    <span style='display: inline-block; width: 16px; height: 16px; background-color: #f46d43; margin-right: 0.6rem; border-radius: 4px;'></span>
                    <span>🟠 <strong>Top 10% - 25%</strong> (&ge; {fmt(q75)}{unit_str})</span>
                </div>
                <div style='display: flex; align-items: center; margin-bottom: 0.4rem;'>
                    <span style='display: inline-block; width: 16px; height: 16px; background-color: #fdae61; margin-right: 0.6rem; border-radius: 4px;'></span>
                    <span>🟡 <strong>Top 25% - 50%</strong> (&ge; {fmt(q50)}{unit_str})</span>
                </div>
                <div style='display: flex; align-items: center; margin-bottom: 0.4rem;'>
                    <span style='display: inline-block; width: 16px; height: 16px; background-color: #abd9e9; margin-right: 0.6rem; border-radius: 4px;'></span>
                    <span>🔵 <strong>Bottom 50% of Active</strong> (&gt; 0 and &lt; {fmt(q50)}{unit_str})</span>
                </div>
                <div style='display: flex; align-items: center;'>
                    <span style='display: inline-block; width: 16px; height: 16px; background-color: #eeeeee; border: 1px solid #ccc; margin-right: 0.6rem; border-radius: 4px;'></span>
                    <span>⚪ <strong>Unprioritized / Zero</strong> (0.0{unit_str})</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
    # Show Top 3 Firesheds
    if len(map_gdf) > 0:
        st.markdown("### 🏆 Top 3 Priority Firesheds")
        top_3 = map_gdf.sort_values(by='Priority_Score', ascending=False).head(3)
        for idx, row in top_3.iterrows():
            st.markdown(f"""
                <div style='background: #eef5db; padding: 0.8rem; border-radius: 8px; margin-bottom: 0.5rem; border-left: 4px solid #17b978;'>
                    <strong>{row['Fireshed_Name']}</strong><br/>
                    ID: {row['Fireshed_ID']} | Score: <strong>{row['Priority_Score']:.3f}</strong>
                </div>
            """, unsafe_allow_html=True)

with col_right:
    st.markdown("### 🗺️ Fireshed Prioritization Map")
    
    if len(map_gdf) == 0:
        st.warning("No firesheds match the selected filters. Please adjust the controls.")
    else:
        # Determine center of map from bounds
        bounds = map_gdf.total_bounds
        center_lat = (bounds[1] + bounds[3]) / 2.0
        center_lon = (bounds[0] + bounds[2]) / 2.0
        
        # Create Folium Map
        # We use CartoDB Positron for a beautiful, clean minimalist base map
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=5,
            tiles="CartoDB positron",
            control_scale=True
        )
        
        if symbology_mode == "Continuous Scale":
            # Setup continuous colormap based on selected layer
            min_val = float(map_gdf[col_name].min())
            max_val = float(map_gdf[col_name].max())
            if max_val <= min_val:
                max_val = min_val + 1.0
                
            colormap = cm.linear.YlOrRd_09.scale(min_val, max_val)
            colormap.caption = f"Continuous {map_layer}"
            colormap.add_to(m)
            
            def style_fn(feature):
                val = feature['properties'].get(col_name, 0.0)
                if val == 0.0:
                    return {
                        'fillColor': '#eeeeee',
                        'color': '#dddddd',
                        'weight': 0.5,
                        'fillOpacity': 0.2
                    }
                return {
                    'fillColor': colormap(val),
                    'color': '#444444',
                    'weight': 1,
                    'fillOpacity': 0.75
                }
        else:
            # Discrete Quantile Symbology on active scores of the selected layer
            active_vals = map_gdf.loc[map_gdf[col_name] > 0.0, col_name]
            if len(active_vals) > 0:
                q50 = active_vals.quantile(0.50)
                q75 = active_vals.quantile(0.75)
                q90 = active_vals.quantile(0.90)
            else:
                q50, q75, q90 = 0.1, 0.25, 0.5
            
            # Proportional step colormap representing the percentile classes directly (0, 50, 75, 90, 100)
            colormap = cm.StepColormap(
                colors=['#abd9e9', '#fdae61', '#f46d43', '#d73027'],
                index=[0, 50, 75, 90, 100],
                vmin=0,
                vmax=100,
                caption=f"Fireshed {map_layer} Percentiles: Bottom 50% | Top 25-50% | Top 10-25% | Top 10%"
            )
            colormap.add_to(m)
            
            def style_fn(feature):
                val = feature['properties'].get(col_name, 0.0)
                if val == 0.0:
                    return {
                        'fillColor': '#eeeeee',
                        'color': '#dddddd',
                        'weight': 0.5,
                        'fillOpacity': 0.2
                    }
                if val >= q90:
                    color = '#d73027'  # Top 10%
                elif val >= q75:
                    color = '#f46d43'  # Top 10-25%
                elif val >= q50:
                    color = '#fdae61'  # Top 25-50%
                else:
                    color = '#abd9e9'  # Bottom 50%
                return {
                    'fillColor': color,
                    'color': '#444444',
                    'weight': 1,
                    'fillOpacity': 0.75
                }
            
        def highlight_fn(feature):
            return {
                'color': '#17b978',
                'weight': 3,
                'fillOpacity': 0.9
            }
            
        # Add GeoJSON layer with hover tooltips
        folium.GeoJson(
            map_gdf.to_json(),
            style_function=style_fn,
            highlight_function=highlight_fn,
            tooltip=folium.GeoJsonTooltip(
                fields=[
                    'Fireshed_ID', 'Fireshed_Name', 'Fireshed_Code', 'Fireshed_State',
                    'Priority_Score', 'Total_Beneficiaries', 'Dry_Forest_Percent', 'Water_Yield_Vol', 'People_Per_Drop'
                ],
                aliases=[
                    'Fireshed ID:', 'Name:', 'Code:', 'State:',
                    'Priority Score:', 'Total Beneficiaries:', 'Dry Forest Coverage %:', 'Water Yield Vol (m³):', 'People-Per-Drop (Efficiency):'
                ],
                localize=True,
                sticky=False,
                labels=True,
                style="""
                    background-color: #F0F2F6;
                    border: 2px solid #1e3d59;
                    border-radius: 8px;
                    box-shadow: 3px 3px 10px rgba(0,0,0,0.2);
                    font-family: Arial;
                    font-size: 12px;
                """
            )
        ).add_to(m)
        
        # Render Folium Map in Streamlit
        st_folium(m, width="100%", height=650, returned_objects=[])
