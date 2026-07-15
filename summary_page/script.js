document.addEventListener('DOMContentLoaded', () => {
    // 1. Pipeline Steps Navigation
    const stepBtns = document.querySelectorAll('.nav-step-btn');
    const stepPanes = document.querySelectorAll('.pipeline-step-pane');

    stepBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active classes
            stepBtns.forEach(b => b.classList.remove('active'));
            stepPanes.forEach(p => p.classList.remove('active'));

            // Add active class to clicked button & corresponding pane
            btn.classList.add('active');
            const stepId = btn.getAttribute('data-step');
            document.getElementById(`step-pane-${stepId}`).classList.add('active');
        });
    });

    // 2. Calibration Simulator Logic
    const socialSelect = document.getElementById('social-metric-select');
    const formulaSelect = document.getElementById('formula-select');
    const w1Slider = document.getElementById('w1-slider');
    const w1Value = document.getElementById('w1-value');
    const w2Value = document.getElementById('w2-value');
    const w2ProgressFill = document.getElementById('w2-progress-fill');
    const formulaExpression = document.getElementById('formula-expression');
    const resultsContainer = document.getElementById('simulated-results');
    const weightsSlidersContainer = document.getElementById('weights-sliders-container');

    // Sample Fireshed raw values and precomputed normalized inputs
    const fireshedData = [
        {
            id: 'fs-card-1',
            name: 'Cascade Headwaters (ID: 3042)',
            popLabel: '1.2M',
            yieldLabel: '850M m³',
            forestLabel: '82%',
            // Precomputed normalized values
            normInputs: {
                ppd: 0.064,
                beneficiaries: 0.489,
                none: 0.372,
                forest: 1.0
            },
            // Raw Multiplicative indicators (Pop/PPD * Forest %)
            rawMult: {
                ppd: 0.00141 * 82, // 0.1156
                beneficiaries: 1.2 * 82, // 98.4
                none: 850 * 82 // 69700
            }
        },
        {
            id: 'fs-card-2',
            name: 'Olympic Rainfall Zone (ID: 1045)',
            popLabel: '50k',
            yieldLabel: '2.1B m³',
            forestLabel: '24%',
            normInputs: {
                ppd: 0.0,
                beneficiaries: 0.0,
                none: 1.0,
                forest: 0.0
            },
            rawMult: {
                ppd: 0.0000238 * 24, // 0.00057
                beneficiaries: 0.05 * 24, // 1.2
                none: 2100 * 24 // 50400
            }
        },
        {
            id: 'fs-card-3',
            name: 'Front Range Interface (ID: 5081)',
            popLabel: '2.4M',
            yieldLabel: '110M m³',
            forestLabel: '65%',
            normInputs: {
                ppd: 1.0,
                beneficiaries: 1.0,
                none: 0.0,
                forest: 0.707
            },
            rawMult: {
                ppd: 0.0218 * 65, // 1.417
                beneficiaries: 2.4 * 65, // 156.0
                none: 110 * 65 // 7150
            }
        }
    ];

    function updateSimulation() {
        const socialMode = socialSelect.value;
        const formulaMode = formulaSelect.value;
        const w1 = parseFloat(w1Slider.value);
        const w2 = 1.0 - w1;

        // UI state management
        w1Value.textContent = w1.toFixed(2);
        w2Value.textContent = w2.toFixed(2);
        w2ProgressFill.style.width = `${w2 * 100}%`;

        // Update slider label based on selected target
        const w1Label = document.getElementById('w1-label');
        if (socialMode === 'ppd') {
            w1Label.innerHTML = '💧 Hydro-Social Weight (w1):';
        } else if (socialMode === 'beneficiaries') {
            w1Label.innerHTML = '👥 Beneficiaries Weight (w1):';
        } else {
            w1Label.innerHTML = '💧 Water Yield Weight (w1):';
        }

        // Manage sliders visibility based on formula mode
        if (formulaMode === 'multiplicative') {
            weightsSlidersContainer.style.display = 'none';
        } else {
            weightsSlidersContainer.style.display = 'block';
        }

        // Update Math Formula text
        let exprText = '';
        if (formulaMode === 'linear') {
            let socialTerm = 'Norm(People_Per_Drop)';
            if (socialMode === 'beneficiaries') socialTerm = 'Norm(Beneficiaries)';
            else if (socialMode === 'none') socialTerm = 'Norm(Water_Yield)';
            
            exprText = `Score = ${w1.toFixed(2)} &middot; ${socialTerm} + ${w2.toFixed(2)} &middot; Norm(Pct_DF)`;
        } else {
            let socialTerm = 'People_Per_Drop';
            if (socialMode === 'beneficiaries') socialTerm = 'Beneficiaries';
            else if (socialMode === 'none') socialTerm = 'Water_Yield';
            
            exprText = `Score = Norm(${socialTerm} &times; Pct_DF)`;
        }
        formulaExpression.innerHTML = exprText;

        // Compute scores for each sample fireshed
        const results = fireshedData.map(fs => {
            let score = 0.0;
            if (formulaMode === 'linear') {
                const socialVal = socialMode === 'ppd' ? fs.normInputs.ppd : (socialMode === 'beneficiaries' ? fs.normInputs.beneficiaries : fs.normInputs.none);
                const forestVal = fs.normInputs.forest;
                score = (w1 * socialVal) + (w2 * forestVal);
            } else {
                const val = socialMode === 'ppd' ? fs.rawMult.ppd : (socialMode === 'beneficiaries' ? fs.rawMult.beneficiaries : fs.rawMult.none);
                const minVal = socialMode === 'ppd' ? 0.00057 : (socialMode === 'beneficiaries' ? 1.2 : 7150);
                const maxVal = socialMode === 'ppd' ? 1.417 : (socialMode === 'beneficiaries' ? 156.0 : 69700);
                score = (val - minVal) / (maxVal - minVal);
            }
            return {
                id: fs.id,
                score: Math.max(0.0, Math.min(1.0, score))
            };
        });

        // Sort by score descending
        results.sort((a, b) => b.score - a.score);

        // Update DOM elements and re-order
        results.forEach((res, index) => {
            const cardEl = document.getElementById(res.id);
            const scoreEl = cardEl.querySelector('.fs-score');
            scoreEl.textContent = `Score: ${res.score.toFixed(3)}`;

            // Apply highlight class to the top ranked item
            if (index === 0) {
                cardEl.classList.add('highlight');
            } else {
                cardEl.classList.remove('highlight');
            }

            // Move card in the container to reflect new rank
            resultsContainer.appendChild(cardEl);
        });
    }

    // Attach listeners
    socialSelect.addEventListener('change', updateSimulation);
    formulaSelect.addEventListener('change', updateSimulation);
    w1Slider.addEventListener('input', updateSimulation);

    // Run initial rendering
    updateSimulation();
});
