/* script.js - Dynamic FPI Scoring & Mapping Engine */

document.addEventListener("DOMContentLoaded", () => {
    // Map State Variables
    let map;
    let geoJsonData = null;
    let leafletLayer = null;
    
    // UI Elements
    const w1Slider = document.getElementById("w1-slider");
    const w1Val = document.getElementById("w1-val");
    const w2Val = document.getElementById("w2-val");
    const w2Progress = document.getElementById("w2-progress");
    const weightsSection = document.getElementById("weights-section");
    const w1Label = document.getElementById("w1-label");
    
    const majorityCheckbox = document.getElementById("majority-filter");
    const thresholdSlider = document.getElementById("threshold-slider");
    const thresholdVal = document.getElementById("threshold-val");
    
    const symbologySelect = document.getElementById("symbology-select");
    const layerSelect = document.getElementById("layer-select");
    
    const statPrioritized = document.getElementById("stat-prioritized");
    const statActive = document.getElementById("stat-active");
    
    const hoverCard = document.getElementById("hover-card");
    const hoverCardBody = hoverCard.querySelector(".hover-card-body");
    const hoverCardHeader = hoverCard.querySelector(".hover-card-header");
    
    const legendItems = document.getElementById("legend-items");
    const legendTitle = document.getElementById("legend-title");

    // Initialize Map
    function initMap() {
        // Center on Western US
        map = L.map("map", {
            zoomControl: true,
            minZoom: 4,
            maxZoom: 10
        }).setView([40.0, -114.0], 5);
        
        // CartoDB Dark Matter Basemap (Aesthetic & High Contrast)
        L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 20
        }).addTo(map);
    }

    // Helper: Compute percentile threshold from sorted list of numbers
    function getPercentile(arr, percentile) {
        if (arr.length === 0) return 0;
        const index = (percentile / 100) * (arr.length - 1);
        const lower = Math.floor(index);
        const upper = Math.ceil(index);
        const weight = index - lower;
        return arr[lower] * (1 - weight) + arr[upper] * weight;
    }

    // Color Ramps for Quantiles
    const COLOR_RAMPS = {
        'Priority_Score': ['#fee5d9', '#fcae91', '#fb6a4a', '#de2d26', '#a50f15'],
        'Total_Beneficiaries': ['#eff3ff', '#bdd7e7', '#6baed6', '#3182bd', '#08519c'],
        'Dry_Forest_Percent': ['#e5f5e0', '#a1d99b', '#74c476', '#31a354', '#006d2c'],
        'Water_Yield_Vol': ['#e0f7fa', '#80deea', '#26c6da', '#00acc1', '#006064'],
        'People_Per_Drop': ['#f3e5f5', '#e1bee7', '#ba68c8', '#8e24aa', '#4a148c']
    };

    // Human-readable labels for legends
    const LAYER_LABELS = {
        'Priority_Score': 'Fireshed Priority Score',
        'Total_Beneficiaries': 'Beneficiaries (People)',
        'Dry_Forest_Percent': 'Dry Forest Coverage %',
        'Water_Yield_Vol': 'Water Yield Volume (m³)',
        'People_Per_Drop': 'People-Per-Drop (Efficiency)'
    };

    // Calculate dynamic scoring on GeoJSON features
    function calculatePriorityScores() {
        if (!geoJsonData) return;
        
        // Read UI values
        const peopleMode = document.querySelector('input[name="people-mode"]:checked').value;
        const aggMode = document.querySelector('input[name="aggregation-mode"]:checked').value;
        const w1 = parseFloat(w1Slider.value);
        const w2 = 1.0 - w1;
        const majorityFilter = majorityCheckbox.checked;
        const minDfThreshold = parseFloat(thresholdSlider.value);
        
        // 1. Initial extraction and PPD computation
        const features = geoJsonData.features;
        features.forEach(f => {
            const yieldVol = parseFloat(f.properties.Fireshed_Water_Yield) || 0.0;
            const forestPct = parseFloat(f.properties.Fireshed_DF_Percent) || 0.0;
            const beneficiaries = parseFloat(f.properties.Total_Beneficiaries) || 0.0;
            const ppd = yieldVol > 0.0 ? beneficiaries / yieldVol : 0.0;
            
            f.properties.Water_Yield_Vol = yieldVol;
            f.properties.Dry_Forest_Percent = forestPct;
            f.properties.Total_Beneficiaries = beneficiaries;
            f.properties.People_Per_Drop = ppd;
            
            // Map the selected population/social metric
            if (peopleMode === 'beneficiaries') {
                f.properties.People_Metric = beneficiaries;
            } else if (peopleMode === 'none') {
                f.properties.People_Metric = yieldVol;
            } else { // 'ppd'
                f.properties.People_Metric = ppd;
            }
        });
        
        // 2. Find min/max values of metrics for normalization
        let minMetric = Infinity;
        let maxMetric = -Infinity;
        let minForest = Infinity;
        let maxForest = -Infinity;
        let minProduct = Infinity;
        let maxProduct = -Infinity;
        
        features.forEach(f => {
            const m = f.properties.People_Metric;
            const fp = f.properties.Dry_Forest_Percent;
            
            if (m < minMetric) minMetric = m;
            if (m > maxMetric) maxMetric = m;
            
            if (fp < minForest) minForest = fp;
            if (fp > maxForest) maxForest = fp;
            
            const prod = m * fp;
            if (prod < minProduct) minProduct = prod;
            if (prod > maxProduct) maxProduct = prod;
        });
        
        // 3. Compute raw scores
        features.forEach(f => {
            const m = f.properties.People_Metric;
            const fp = f.properties.Dry_Forest_Percent;
            
            const normMetric = (maxMetric > minMetric) ? (m - minMetric) / (maxMetric - minMetric) : 0.0;
            const normForest = (maxForest > minForest) ? (fp - minForest) / (maxForest - minForest) : 0.0;
            
            let rawScore = 0.0;
            
            if (aggMode === 'multiplicative') {
                if (peopleMode === 'none') {
                    // Multiplicative for none: normalize the product of raw variables
                    rawScore = (maxProduct > minProduct) ? (m * fp - minProduct) / (maxProduct - minProduct) : 0.0;
                } else {
                    rawScore = normMetric * normForest;
                }
            } else { // linear
                if (peopleMode === 'none') {
                    // Linear for none: apply the geometric penalty product
                    rawScore = (w1 * normMetric + w2 * normForest) * normMetric * normForest;
                } else {
                    rawScore = w1 * normMetric + w2 * normForest;
                }
            }
            
            // Apply Majority Forest Filter
            if (majorityFilter && fp < 50.0) {
                rawScore = 0.0;
            }
            
            f.properties.Priority_Score_Raw = rawScore;
        });
        
        // 4. Min-max normalize raw scores to final Priority_Score
        let minScore = Infinity;
        let maxScore = -Infinity;
        features.forEach(f => {
            const s = f.properties.Priority_Score_Raw;
            if (s < minScore) minScore = s;
            if (s > maxScore) maxScore = s;
        });
        
        features.forEach(f => {
            const raw = f.properties.Priority_Score_Raw;
            let finalScore = (maxScore > minScore) ? (raw - minScore) / (maxScore - minScore) : 0.0;
            
            // Apply Dry Forest Cover Threshold Slider Mask
            if (f.properties.Dry_Forest_Percent < minDfThreshold) {
                finalScore = 0.0;
            }
            
            f.properties.Priority_Score = finalScore;
        });
    }

    // Determine the color of a polygon based on active layer and symbology settings
    function styleFeature(feature) {
        const layer = layerSelect.value;
        const val = parseFloat(feature.properties[layer]) || 0.0;
        const styleMode = symbologySelect.value;
        
        let color = '#eeeeee';
        
        if (val > 0.0) {
            if (styleMode === 'quantile') {
                color = getQuantileColor(val, layer);
            } else {
                color = getContinuousColor(val, layer);
            }
        }
        
        const opacity = val > 0.0 ? 0.65 : 0.15;
        const weight = val > 0.0 ? 0.6 : 0.3;
        const borderColor = val > 0.0 ? '#1e2538' : '#777777';
        
        return {
            fillColor: color,
            fillOpacity: opacity,
            weight: weight,
            color: borderColor,
            dashArray: ''
        };
    }

    // Helper: Get color from continuous HSL scaling
    function getContinuousColor(val, layer) {
        // Collect all non-zero values for current layer to scale bounds
        const vals = geoJsonData.features.map(f => f.properties[layer]).filter(v => v > 0.0);
        if (vals.length === 0) return '#eeeeee';
        
        const minVal = Math.min(...vals);
        const maxVal = Math.max(...vals);
        const norm = (maxVal > minVal) ? (val - minVal) / (maxVal - minVal) : 0.0;
        
        if (layer === 'Priority_Score') {
            // HSL: Red (0) to Yellow (50)
            const h = norm * 50;
            return `hsl(${h}, 90%, 45%)`;
        } else if (layer === 'Total_Beneficiaries') {
            // Blue
            return `hsl(210, 85%, ${80 - norm * 40}%)`;
        } else if (layer === 'Dry_Forest_Percent') {
            // Green
            return `hsl(140, 80%, ${75 - norm * 35}%)`;
        } else if (layer === 'Water_Yield_Vol') {
            // Cyan-Blue
            const h = 180 + norm * 40;
            return `hsl(${h}, 85%, ${75 - norm * 30}%)`;
        } else if (layer === 'People_Per_Drop') {
            // Purple-Magenta
            const h = 265 + norm * 50;
            return `hsl(${h}, 85%, ${70 - norm * 30}%)`;
        }
        return '#eeeeee';
    }

    // Cache percentiles list to optimize style calls
    let activePercentiles = {};

    function precomputeQuantiles() {
        if (!geoJsonData) return;
        const layer = layerSelect.value;
        
        // Extract active non-zero values
        const vals = geoJsonData.features
            .map(f => f.properties[layer])
            .filter(v => v > 0.0)
            .sort((a, b) => a - b);
            
        activePercentiles = {
            vals: vals,
            p25: getPercentile(vals, 25),
            p50: getPercentile(vals, 50),
            p75: getPercentile(vals, 75),
            p90: getPercentile(vals, 90)
        };
    }

    function getQuantileColor(val, layer) {
        const p = activePercentiles;
        if (!p.vals || p.vals.length === 0) return '#eeeeee';
        
        let colorClass = 0;
        if (val >= p.p90) colorClass = 4;
        else if (val >= p.p75) colorClass = 3;
        else if (val >= p.p50) colorClass = 2;
        else if (val >= p.p25) colorClass = 1;
        
        const ramp = COLOR_RAMPS[layer] || COLOR_RAMPS['Priority_Score'];
        return ramp[colorClass];
    }

    // Update the Map Legend HTML
    function updateLegend() {
        const layer = layerSelect.value;
        const styleMode = symbologySelect.value;
        
        legendTitle.textContent = LAYER_LABELS[layer] || layer;
        legendItems.innerHTML = '';
        
        if (styleMode === 'quantile') {
            const p = activePercentiles;
            const ramp = COLOR_RAMPS[layer] || COLOR_RAMPS['Priority_Score'];
            
            if (!p.vals || p.vals.length === 0) {
                legendItems.innerHTML = '<div class="legend-label">No active data available</div>';
                return;
            }
            
            const formatFn = getFormatter(layer);
            const classes = [
                { label: `Bottom 25% (0 - ${formatFn(p.p25)})`, color: ramp[0] },
                { label: `25% - 50% (${formatFn(p.p25)} - ${formatFn(p.p50)})`, color: ramp[1] },
                { label: `50% - 75% (${formatFn(p.p50)} - ${formatFn(p.p75)})`, color: ramp[2] },
                { label: `Top 25% (${formatFn(p.p75)} - ${formatFn(p.p90)})`, color: ramp[3] },
                { label: `Top 10% (≥ ${formatFn(p.p90)})`, color: ramp[4] }
            ];
            
            classes.forEach(c => {
                const row = document.createElement("div");
                row.className = "legend-row";
                row.innerHTML = `<div class="legend-color" style="background-color: ${c.color}"></div><div class="legend-label">${c.label}</div>`;
                legendItems.appendChild(row);
            });
        } else {
            // Continuous gradient legend helper
            const formatFn = getFormatter(layer);
            const vals = activePercentiles.vals;
            if (!vals || vals.length === 0) {
                legendItems.innerHTML = '<div class="legend-label">No active data available</div>';
                return;
            }
            
            const minStr = formatFn(vals[0]);
            const maxStr = formatFn(vals[vals.length - 1]);
            
            // Build visual color ramp
            let gradientStr = '';
            if (layer === 'Priority_Score') {
                gradientStr = 'linear-gradient(to right, hsl(0, 90%, 45%), hsl(50, 90%, 60%))';
            } else if (layer === 'Total_Beneficiaries') {
                gradientStr = 'linear-gradient(to right, hsl(210, 85%, 80%), hsl(210, 85%, 40%))';
            } else if (layer === 'Dry_Forest_Percent') {
                gradientStr = 'linear-gradient(to right, hsl(140, 80%, 75%), hsl(140, 80%, 40%))';
            } else if (layer === 'Water_Yield_Vol') {
                gradientStr = 'linear-gradient(to right, hsl(180, 85%, 75%), hsl(220, 85%, 45%))';
            } else if (layer === 'People_Per_Drop') {
                gradientStr = 'linear-gradient(to right, hsl(265, 85%, 70%), hsl(315, 85%, 40%))';
            }
            
            legendItems.innerHTML = `
                <div style="height: 12px; width: 100%; border-radius: 3px; background: ${gradientStr}; border: 1px solid var(--border-glass)"></div>
                <div style="display: flex; justify-content: space-between; font-size: 10px; color: var(--text-secondary); margin-top: 4px;">
                    <span>Min: ${minStr}</span>
                    <span>Max: ${maxStr}</span>
                </div>
            `;
        }
    }

    function getFormatter(layer) {
        if (layer === 'Priority_Score' || layer === 'People_Per_Drop') {
            return (val) => val.toFixed(3);
        } else if (layer === 'Dry_Forest_Percent') {
            return (val) => `${val.toFixed(1)}%`;
        } else if (layer === 'Total_Beneficiaries') {
            return (val) => Math.round(val).toLocaleString();
        } else if (layer === 'Water_Yield_Vol') {
            return (val) => {
                if (val >= 1e9) return `${(val / 1e9).toFixed(2)}B m³`;
                if (val >= 1e6) return `${(val / 1e6).toFixed(1)}M m³`;
                return `${Math.round(val).toLocaleString()} m³`;
            };
        }
        return (val) => val.toString();
    }

    // Update sidebar statistics
    function updateStats() {
        if (!geoJsonData) return;
        
        const total = geoJsonData.features.length;
        const prioritized = geoJsonData.features.filter(f => f.properties.Priority_Score > 0.0).length;
        
        statActive.textContent = total.toLocaleString();
        statPrioritized.textContent = prioritized.toLocaleString();
    }

    // Hover cards event handling
    function onEachFeature(feature, layer) {
        layer.on({
            mouseover: (e) => {
                const l = layerSelect.value;
                
                // Highlight polygon border
                layer.setStyle({
                    weight: 2.0,
                    color: '#00ffcc',
                    fillOpacity: 0.8
                });
                
                // Bring to front
                if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) {
                    layer.bringToFront();
                }
                
                // Update Hover Card contents
                document.getElementById("hover-name").textContent = feature.properties.Fireshed_Name || 'Unknown Fireshed';
                document.getElementById("hover-score").textContent = feature.properties.Priority_Score.toFixed(3);
                document.getElementById("hover-beneficiaries").textContent = Math.round(feature.properties.Total_Beneficiaries).toLocaleString();
                document.getElementById("hover-forest").textContent = `${feature.properties.Dry_Forest_Percent.toFixed(1)}%`;
                
                const yieldVal = feature.properties.Water_Yield_Vol;
                document.getElementById("hover-yield").textContent = getFormatter('Water_Yield_Vol')(yieldVal);
                document.getElementById("hover-ppd").textContent = feature.properties.People_Per_Drop.toFixed(4);
                
                hoverCardHeader.style.display = 'none';
                hoverCardBody.style.display = 'block';
            },
            mouseout: (e) => {
                // Reset style
                leafletLayer.resetStyle(layer);
                
                hoverCardHeader.style.display = 'block';
                hoverCardBody.style.display = 'none';
            }
        });
    }

    // Core Redraw Loop: runs score calculations, quantile binnings, styling updates
    function redrawMap() {
        if (!geoJsonData) return;
        
        calculatePriorityScores();
        precomputeQuantiles();
        
        if (leafletLayer) {
            leafletLayer.setStyle(styleFeature);
        } else {
            leafletLayer = L.geoJSON(geoJsonData, {
                style: styleFeature,
                onEachFeature: onEachFeature
            }).addTo(map);
        }
        
        updateLegend();
        updateStats();
    }

    // UI state adjustments
    function handleUIChanges() {
        const peopleMode = document.querySelector('input[name="people-mode"]:checked').value;
        const aggMode = document.querySelector('input[name="aggregation-mode"]:checked').value;
        
        // Toggle slider labels and visibility
        if (aggMode === 'multiplicative') {
            weightsSection.style.display = 'none';
        } else {
            weightsSection.style.display = 'block';
            if (peopleMode === 'ppd') {
                w1Label.innerHTML = '💧 Hydro-Social Weight (w1)';
            } else if (peopleMode === 'beneficiaries') {
                w1Label.innerHTML = '👥 Beneficiaries Weight (w1)';
            } else {
                w1Label.innerHTML = '💧 Water Yield Weight (w1)';
            }
        }
        
        // Keep w2 matching w1
        const w1 = parseFloat(w1Slider.value);
        const w2 = 1.0 - w1;
        w1Val.textContent = w1.toFixed(2);
        w2Val.textContent = w2.toFixed(2);
        w2Progress.style.width = `${w2 * 100}%`;
        
        thresholdVal.textContent = `${thresholdSlider.value}%`;
    }

    // Register UI event listeners
    function registerListeners() {
        // Radio buttons
        document.querySelectorAll('input[name="people-mode"]').forEach(r => {
            r.addEventListener("change", () => {
                handleUIChanges();
                redrawMap();
            });
        });
        
        document.querySelectorAll('input[name="aggregation-mode"]').forEach(r => {
            r.addEventListener("change", () => {
                handleUIChanges();
                redrawMap();
            });
        });
        
        // Sliders
        w1Slider.addEventListener("input", () => {
            handleUIChanges();
            redrawMap();
        });
        
        thresholdSlider.addEventListener("input", () => {
            handleUIChanges();
            redrawMap();
        });
        
        // Checkboxes
        majorityCheckbox.addEventListener("change", redrawMap);
        
        // Select dropdowns
        symbologySelect.addEventListener("change", redrawMap);
        layerSelect.addEventListener("change", redrawMap);
    }

    // Fetch and load the GeoJSON file
    function loadData() {
        fetch("firesheds.geojson")
            .then(res => {
                if (!res.ok) throw new Error("Could not find GeoJSON file.");
                return res.json();
            })
            .then(data => {
                geoJsonData = data;
                handleUIChanges();
                redrawMap();
            })
            .catch(err => {
                console.error(err);
                alert("⚠️ GeoJSON boundaries file (firesheds.geojson) not found. Make sure you run the python preparation script first.");
            });
    }

    // Start App
    initMap();
    registerListeners();
    loadData();
});
