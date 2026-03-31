const API_URL = 'http://localhost:5002/api/analyze';

/* ===== Toast 通知 ===== */
const TOAST_ICONS = {
    error:   '<svg viewBox="0 0 20 20" fill="currentColor"><circle cx="10" cy="10" r="9" fill="none" stroke="currentColor" stroke-width="1.5"/><line x1="10" y1="6" x2="10" y2="11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="10" cy="14" r="1" /></svg>',
    warning: '<svg viewBox="0 0 20 20" fill="currentColor"><path d="M10 2 L19 17 H1 Z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><line x1="10" y1="8" x2="10" y2="12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="10" cy="14.5" r="1"/></svg>',
    success: '<svg viewBox="0 0 20 20" fill="currentColor"><circle cx="10" cy="10" r="9" fill="none" stroke="currentColor" stroke-width="1.5"/><polyline points="6,10 9,13 14,7" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
};
function showToast(message, type = 'error', duration = 4000) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML =
        `<span class="toast-icon">${TOAST_ICONS[type] || TOAST_ICONS.error}</span>` +
        `<span class="toast-body">${message}</span>` +
        `<button class="toast-close">&times;</button>` +
        `<span class="toast-progress" style="animation-duration:${duration}ms"></span>`;
    toast.querySelector('.toast-close').onclick = () => dismissToast(toast);
    container.appendChild(toast);
    // 最多保留 5 条
    while (container.children.length > 5) container.removeChild(container.firstChild);
    const timer = setTimeout(() => dismissToast(toast), duration);
    toast._timer = timer;
}
function dismissToast(toast) {
    if (toast._dismissed) return;
    toast._dismissed = true;
    clearTimeout(toast._timer);
    toast.classList.add('toast-exit');
    toast.addEventListener('animationend', () => toast.remove());
}

let uploadedImage = null;
let analysisResult = null;
let activeStep = 0;

const STEP_KEYS = [
    'step1_roi_extraction',
    'step2_crop',
    'step3_split',
    'step5_color_change'
];

const IMG_LABELS = {
    binary: '二值化',
    contours: '轮廓检测',
    roi: 'ROI 区域',
    hole_detection: '黑洞定位',
    cropped: '裁剪结果',
    split_view: '左右分割',
    grid_overlay: '网格划分',
    heatmap: '色差热力图',
    highlighted_area: '变色标注'
};

document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
});

function initEventListeners() {
    const thresholdInput = document.getElementById('threshold');
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('file-input');
    const previewBox = document.getElementById('preview');

    thresholdInput.addEventListener('input', (e) => {
        document.getElementById('threshold-value').textContent = e.target.value;
    });

    uploadArea.addEventListener('click', () => fileInput.click());
    previewBox.addEventListener('click', () => fileInput.click());

    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });
    uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) handleImageUpload(file);
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files[0]) handleImageUpload(e.target.files[0]);
    });

    document.getElementById('analyze-btn').addEventListener('click', startAnalysis);
}

function handleImageUpload(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        uploadedImage = e.target.result;
        document.getElementById('original-image').src = uploadedImage;
        document.getElementById('upload-area').style.display = 'none';
        document.getElementById('preview').style.display = 'block';
        document.getElementById('analyze-btn').disabled = false;
    };
    reader.readAsDataURL(file);
}

function setGlobalStatus(state, text) {
    const dot = document.getElementById('global-status-dot');
    const label = document.getElementById('global-status-text');
    if (dot) { dot.className = 'status-indicator ' + state; }
    if (label) { label.textContent = text; }
}

async function startAnalysis() {
    if (!uploadedImage) return;

    const threshold = parseInt(document.getElementById('threshold').value);
    const gridSize = parseInt(document.getElementById('grid-size').value);

    document.getElementById('loading').style.display = 'block';
    document.getElementById('analyze-btn').disabled = true;
    document.getElementById('visualization').style.display = 'none';
    document.getElementById('result-section').style.display = 'none';
    document.getElementById('empty-state').style.display = 'none';
    setGlobalStatus('running', '分析中');

    try {
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: uploadedImage, threshold, grid_size: gridSize })
        });
        const result = await response.json();

        if (result.success) {
            analysisResult = result;
            displayResults(result);
            setGlobalStatus('done', '分析完成');
        } else {
            showToast('分析失败: ' + result.error, 'error');
            document.getElementById('empty-state').style.display = 'flex';
            setGlobalStatus('stopped', '出错');
        }
    } catch (error) {
        showToast('请求失败: ' + error.message, 'error');
        document.getElementById('empty-state').style.display = 'flex';
        setGlobalStatus('stopped', 'ERROR');
    } finally {
        document.getElementById('loading').style.display = 'none';
        document.getElementById('analyze-btn').disabled = false;
    }
}

function displayResults(result) {
    buildStepper(result.steps);
    showStep(0);
    document.getElementById('visualization').style.display = 'flex';
    displayResultCards(result.final_results);
    document.getElementById('result-section').style.display = 'grid';
}

function displayResultCards(r) {
    const fmtLab = (arr) =>
        `L ${arr[0]}  a ${arr[1]}  b ${arr[2]}`;
    document.getElementById('left-lab-value').textContent = fmtLab(r.left_lab);
    document.getElementById('right-lab-value').textContent = fmtLab(r.right_lab);
    document.getElementById('delta-e-value').textContent = r.overall_delta_e.toFixed(2);
    document.getElementById('ratio-value').textContent = (r.color_change_ratio * 100).toFixed(1) + '%';
    document.getElementById('ratio-label').textContent =
        `${r.changed_cells} / ${r.total_cells}  THR ${r.threshold_used}`;
}

function buildStepper(steps) {
    const stepper = document.getElementById('stepper');
    stepper.innerHTML = '';

    // 只取实际存在的步骤，重新建连续下标映射
    const validSteps = STEP_KEYS.filter(key => steps[key]);

    validSteps.forEach((key, i) => {
        const step = steps[key];

        const node = document.createElement('div');
        node.className = 'step-node';
        node.dataset.index = i;
        node.innerHTML = `
            <div class="step-dot-wrap">
                <div class="step-dot" id="dot-${i}">${i + 1}</div>
                <div class="step-label">${step.title}</div>
            </div>`;
        node.addEventListener('click', () => showStep(i));
        stepper.appendChild(node);

        if (i < validSteps.length - 1) {
            const conn = document.createElement('div');
            conn.className = 'step-connector';
            conn.id = `conn-${i}`;
            stepper.appendChild(conn);
        }
    });

    // 保存有效步骤列表供 showStep 使用
    window._validStepKeys = validSteps;
}

function showStep(index) {
    activeStep = index;
    const steps = analysisResult.steps;
    const keys = window._validStepKeys || STEP_KEYS;

    // 更新步骤条状态
    keys.forEach((_, i) => {
        const dot = document.getElementById(`dot-${i}`);
        const node = dot?.closest('.step-node');
        if (!dot) return;
        dot.className = 'step-dot' + (i < index ? ' done' : i === index ? ' active' : '');
        node.className = 'step-node' + (i === index ? ' active' : i < index ? ' done' : '');
        if (i < keys.length - 1) {
            const conn = document.getElementById(`conn-${i}`);
            if (conn) conn.className = 'step-connector' + (i < index ? ' done' : '');
        }
    });

    // 渲染步骤内容
    const step = steps[keys[index]];
    if (!step) return;

    const imagesHtml = Object.entries(step.images).map(([key, b64]) => `
        <div class="step-img-wrap">
            <img src="data:image/png;base64,${b64}" alt="${IMG_LABELS[key] || key}">
            <div class="step-img-label">${IMG_LABELS[key] || key}</div>
        </div>`).join('');

    const dataHtml = buildDataHtml(step.data);

    const prevBtn = index > 0
        ? `<button class="step-nav-btn" onclick="showStep(${index - 1})">← 上一步</button>` : '';
    const nextBtn = index < keys.length - 1
        ? `<button class="step-nav-btn primary" onclick="showStep(${index + 1})">下一步 →</button>` : '';

    document.getElementById('step-content').innerHTML = `
        <div class="step-content-inner">
            <div class="step-content-header">
                <h3>${step.title}</h3>
                <p>${step.description}</p>
            </div>
            ${imagesHtml ? `<div class="step-images">${imagesHtml}</div>` : ''}
            ${dataHtml ? `<div class="step-data-box">${dataHtml}</div>` : ''}
            <div class="step-nav">${prevBtn}${nextBtn}</div>
        </div>`;
}

function buildDataHtml(data) {
    if (!data) return '';
    const labKeys = ['left_lab', 'right_lab'];

    // step3: LAB 均值 + 整体 ΔE
    if ('delta_e' in data && 'formula' in data) {
        const fmtLab = (arr) => `L ${arr[0]} / a ${arr[1]} / b ${arr[2]}`;
        return `
            <div class="data-row"><span class="data-key">公式</span><span class="data-val highlight">${data.formula}</span></div>
            <div class="data-row"><span class="data-key">左侧 LAB（基准）</span><span class="data-val highlight">${fmtLab(data.left_lab)}</span></div>
            <div class="data-row"><span class="data-key">右侧 LAB</span><span class="data-val highlight">${fmtLab(data.right_lab)}</span></div>
            <div class="data-row"><span class="data-key">整体 ΔE</span><span class="data-val" style="font-size:1.4em;color:var(--orange)">${data.delta_e}</span></div>`;
    }

    // step5: 最终比例
    if ('ratio' in data) {
        return `
            <div class="data-row"><span class="data-key">阈值</span><span class="data-val">ΔE > ${data.threshold}</span></div>
            <div class="data-row"><span class="data-key">超阈值网格</span><span class="data-val">${data.changed_cells} / ${data.total_cells}</span></div>
            <div class="data-row"><span class="data-key">变色比例</span><span class="data-val" style="font-size:1.4em;color:var(--red)">${data.ratio}%</span></div>`;
    }

    return Object.entries(data).map(([k, v]) => {
        let val = Array.isArray(v) ? (labKeys.includes(k) ? `L=${v[0]}  a=${v[1]}  b=${v[2]}` : JSON.stringify(v)) : v;
        const isHighlight = labKeys.includes(k);
        return `<div class="data-row"><span class="data-key">${k}</span><span class="data-val${isHighlight ? ' highlight' : ''}">${val}</span></div>`;
    }).join('');
}
