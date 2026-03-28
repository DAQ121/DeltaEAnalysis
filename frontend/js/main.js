const API_URL = 'http://localhost:5002/api/analyze';

let uploadedImage = null;

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
});

function initEventListeners() {
    const thresholdInput = document.getElementById('threshold');
    const thresholdValue = document.getElementById('threshold-value');
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('file-input');
    const analyzeBtn = document.getElementById('analyze-btn');
    const referenceMode = document.getElementById('reference-mode');
    const manualLab = document.getElementById('manual-lab');

    thresholdInput.addEventListener('input', (e) => {
        thresholdValue.textContent = e.target.value;
    });

    referenceMode.addEventListener('change', (e) => {
        manualLab.style.display = e.target.value === 'manual' ? 'block' : 'none';
    });

    uploadArea.addEventListener('click', () => fileInput.click());

    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) {
            handleImageUpload(file);
        }
    });

    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            handleImageUpload(file);
        }
    });

    analyzeBtn.addEventListener('click', startAnalysis);
}

function handleImageUpload(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        uploadedImage = e.target.result;
        const preview = document.getElementById('preview');
        const originalImage = document.getElementById('original-image');
        originalImage.src = uploadedImage;
        preview.style.display = 'block';
        document.getElementById('analyze-btn').disabled = false;
    };
    reader.readAsDataURL(file);
}

async function startAnalysis() {
    if (!uploadedImage) return;

    const threshold = parseInt(document.getElementById('threshold').value);
    const gridSize = parseInt(document.getElementById('grid-size').value);
    const referenceMode = document.getElementById('reference-mode').value;

    let requestData = {
        image: uploadedImage,
        threshold: threshold,
        grid_size: gridSize,
        reference_ratio: 0.15,
        fill_holes: document.getElementById('fill-holes').checked
    };

    if (referenceMode === 'manual') {
        requestData.manual_lab = [
            parseFloat(document.getElementById('lab-l').value),
            parseFloat(document.getElementById('lab-a').value),
            parseFloat(document.getElementById('lab-b').value)
        ];
    }

    document.getElementById('loading').style.display = 'block';
    document.getElementById('analyze-btn').disabled = true;
    document.getElementById('visualization').style.display = 'none';
    document.getElementById('result-section').style.display = 'none';

    try {
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });

        const result = await response.json();

        if (result.success) {
            displayResults(result);
        } else {
            alert('分析失败: ' + result.error);
        }
    } catch (error) {
        alert('请求失败: ' + error.message);
    } finally {
        document.getElementById('loading').style.display = 'none';
        document.getElementById('analyze-btn').disabled = false;
    }
}

function displayResults(result) {
    displaySteps(result.steps);
    displayFinalResults(result.final_results);
}

function displaySteps(steps) {
    const container = document.getElementById('steps-container');
    container.innerHTML = '';

    const stepOrder = [
        'step1_roi_extraction',
        'step2_reference_color',
        'step3_grid_division',
        'step4_delta_e_calculation',
        'step5_color_change_detection'
    ];

    stepOrder.forEach((stepKey, index) => {
        const step = steps[stepKey];
        if (!step) return;

        setTimeout(() => {
            const stepCard = createStepCard(step);
            container.appendChild(stepCard);
        }, index * 300);
    });

    document.getElementById('visualization').style.display = 'block';
}

function createStepCard(step) {
    const card = document.createElement('div');
    card.className = 'step-card';

    const title = document.createElement('h3');
    title.textContent = step.title;
    card.appendChild(title);

    const desc = document.createElement('p');
    desc.textContent = step.description;
    card.appendChild(desc);

    Object.values(step.images).forEach(imgBase64 => {
        const img = document.createElement('img');
        img.src = 'data:image/png;base64,' + imgBase64;
        card.appendChild(img);
    });

    if (step.data) {
        const dataDiv = document.createElement('div');
        dataDiv.style.fontSize = '0.85em';
        dataDiv.style.color = '#666';
        dataDiv.style.marginTop = '10px';
        dataDiv.textContent = JSON.stringify(step.data, null, 2);
        card.appendChild(dataDiv);
    }

    return card;
}

function displayFinalResults(results) {
    setTimeout(() => {
        document.getElementById('delta-e-value').textContent = results.changed_area_delta_e.toFixed(2);
        document.getElementById('ratio-value').textContent = (results.color_change_ratio * 100).toFixed(1) + '%';

        const statusDiv = document.getElementById('result-status');
        const statusText = document.getElementById('status-text');
        const statusDesc = document.getElementById('status-desc');

        if (results.experiment_success) {
            statusDiv.className = 'result-status success';
            statusText.textContent = '✓ 实验成功';
            statusDesc.textContent = `色差值超过设定阈值 (${results.threshold_used})`;
        } else {
            statusDiv.className = 'result-status failure';
            statusText.textContent = '✗ 实验失败';
            statusDesc.textContent = `色差值未达到设定阈值 (${results.threshold_used})`;
        }

        document.getElementById('result-section').style.display = 'block';
    }, 1500);
}





