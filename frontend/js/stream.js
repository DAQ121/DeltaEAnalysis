const STREAM_API = 'http://localhost:5002/api/stream';

let currentSessionId = null;
let currentEventSource = null;
let modalAnalysisResult = null;
let modalActiveStep = 0;
const STREAM_STEP_KEYS = ['step1_roi_extraction', 'step2_crop', 'step3_split', 'step5_color_change'];
const STREAM_IMG_LABELS = {
    binary: '二值化', contours: '轮廓检测', roi: 'ROI 区域',
    hole_detection: '黑洞定位', cropped: '裁剪结果', split_view: '左右分割',
    grid_overlay: '网格划分', heatmap: '色差热力图', highlighted_area: '变色标注'
};

function setGlobalStatus(state, text) {
    const dot = document.getElementById('global-status-dot');
    const label = document.getElementById('global-status-text');
    if (dot) dot.className = 'status-indicator ' + state;
    if (label) label.textContent = text;
}

// ===== Tab 切换 =====
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(p => p.style.display = 'none');
            btn.classList.add('active');
            document.getElementById('tab-' + btn.dataset.tab).style.display = 'flex';
        });
    });

    document.getElementById('s-threshold').addEventListener('input', e => {
        document.getElementById('s-threshold-value').textContent = e.target.value;
    });

    document.getElementById('s-start-btn').addEventListener('click', startStream);
    document.getElementById('s-stop-btn').addEventListener('click', stopStream);
    document.getElementById('modal-close').addEventListener('click', closeModal);
    document.getElementById('detail-modal').addEventListener('click', e => {
        if (e.target === document.getElementById('detail-modal')) closeModal();
    });
    document.getElementById('result-modal-close').addEventListener('click', closeResultModal);
    document.getElementById('result-modal').addEventListener('click', e => {
        if (e.target === document.getElementById('result-modal')) closeResultModal();
    });
});

// ===== 启动检测 =====
async function startStream() {
    const source = document.getElementById('s-source').value.trim();
    if (!source) { showToast('请填写视频源路径或 RTSP 地址', 'warning'); return; }

    const config = {
        source,
        interval: parseFloat(document.getElementById('s-interval').value),
        threshold: parseFloat(document.getElementById('s-threshold').value),
        grid_size: parseInt(document.getElementById('s-grid-size').value)
    };

    try {
        const res = await fetch(`${STREAM_API}/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        const data = await res.json();
        if (!data.success) { showToast('启动失败: ' + data.error, 'error'); return; }

        currentSessionId = data.session_id;
        initStreamUI();
        connectSSE(currentSessionId);
    } catch (e) {
        showToast('请求失败: ' + e.message, 'error');
    }
}

function initStreamUI() {
    document.getElementById('s-empty').style.display = 'none';
    document.getElementById('s-final').style.display = 'none';
    document.getElementById('s-timeline').innerHTML = '';
    document.getElementById('s-preview').style.display = 'flex';
    document.getElementById('s-timeline-wrap').style.display = 'flex';
    document.getElementById('s-status').style.display = 'flex';
    document.getElementById('s-status-dot').className = 'status-indicator running';
    document.getElementById('s-status-text').textContent = '检测中';
    document.getElementById('s-frame-count').textContent = '已抓 0 帧';
    document.getElementById('s-view-result-btn-inline').style.display = 'none';
    document.getElementById('s-start-btn').style.display = 'none';
    document.getElementById('s-stop-btn').style.display = 'flex';
    setGlobalStatus('running', '流检测中');

    const canvas = document.getElementById('s-preview-canvas');
    canvas.style.display = 'none';
    let img = document.getElementById('s-preview-img');
    if (!img) {
        img = document.createElement('img');
        img.id = 's-preview-img';
        img.style.width = '100%';
        img.style.height = '100%';
        img.style.objectFit = 'contain';
        document.getElementById('s-preview').appendChild(img);
    }
    img.src = `${STREAM_API}/video/${currentSessionId}`;
    img.style.display = 'block';
}

// ===== SSE 连接 =====
function connectSSE(sessionId) {
    if (currentEventSource) currentEventSource.close();
    currentEventSource = new EventSource(`${STREAM_API}/events/${sessionId}`);

    currentEventSource.onmessage = e => {
        const event = JSON.parse(e.data);
        if (event.type === 'frame') onFrame(event.data);
        else if (event.type === 'frame_error') onFrameError(event);
        else if (event.type === 'completed') { onCompleted(event.data); }
        else if (event.type === 'stopped') onStopped();
        else if (event.type === 'error') onError(event.message);
    };

    currentEventSource.onerror = () => {
        currentEventSource.close();
        setStatusStopped();
    };
}

// ===== 停止检测 =====
async function stopStream() {
    if (!currentSessionId) return;
    await fetch(`${STREAM_API}/stop/${currentSessionId}`, { method: 'POST' });
    if (currentEventSource) currentEventSource.close();
    setStatusStopped();
}

function setStatusStopped() {
    document.getElementById('s-status-dot').className = 'status-indicator stopped';
    document.getElementById('s-status-text').textContent = '已停止';
    document.getElementById('s-start-btn').style.display = 'flex';
    document.getElementById('s-stop-btn').style.display = 'none';
    setGlobalStatus('idle', '待机');
}

// ===== 事件处理 =====
function onFrame(data) {
    const count = document.getElementById('s-timeline').children.length + 1;
    document.getElementById('s-frame-count').textContent = `已抓 ${count} 帧`;
    appendFrameCard(data);
    updatePreview(data.thumbnail);
    const tl = document.getElementById('s-timeline');
    tl.scrollLeft = tl.scrollWidth;
}

function updatePreview(thumbnail) {
    // 实时视频流已通过 img 标签显示，不再需要 canvas 更新
}

function onFrameError(event) {
    appendErrorCard(event);
}

function onCompleted(data) {
    if (currentEventSource) currentEventSource.close();
    document.getElementById('s-status-dot').className = 'status-indicator done';
    document.getElementById('s-status-text').textContent = '已发现变色';
    document.getElementById('s-start-btn').style.display = 'flex';
    document.getElementById('s-stop-btn').style.display = 'none';
    setGlobalStatus('done', '检测完成');
    showFinalResult(data.result);
}

function onStopped() {
    setStatusStopped();
}

function onError(msg) {
    document.getElementById('s-status-dot').className = 'status-indicator stopped';
    document.getElementById('s-status-text').textContent = '错误: ' + msg;
    document.getElementById('s-start-btn').style.display = 'flex';
    document.getElementById('s-stop-btn').style.display = 'none';
    setGlobalStatus('stopped', '出错');
}

// ===== 渲染帧卡片 =====
function appendFrameCard(data) {
    const r = data.result;
    const changed = r.is_changed;
    const card = document.createElement('div');
    card.className = 'frame-card' + (changed ? ' changed' : '');
    card.innerHTML = `
        <div class="frame-thumb-wrap">
            <img class="frame-thumb" src="data:image/jpeg;base64,${data.thumbnail}" alt="帧${data.frame_index}">
            ${changed ? '<div class="frame-changed-badge">变色</div>' : ''}
        </div>
        <div class="frame-time">${data.capture_time}s</div>
        <div class="frame-metrics">
            <div class="fm-row"><span class="fm-key">ΔE</span><span class="fm-val ${changed ? 'green' : ''}">${r.deltaE.toFixed(2)}</span></div>
            <div class="fm-row"><span class="fm-key">ΔE/阈值</span><span class="fm-val">${(r.deltaE_ratio * 100).toFixed(1)}%</span></div>
            <div class="fm-row"><span class="fm-key">变色区域</span><span class="fm-val">${(r.change_ratio * 100).toFixed(1)}%</span></div>
        </div>
        <button class="detail-btn" data-index="${data.frame_index}">详情</button>`;
    card.querySelector('.detail-btn').addEventListener('click', () => openModal(data.frame_index));
    document.getElementById('s-timeline').appendChild(card);
}

function appendErrorCard(event) {
    const card = document.createElement('div');
    card.className = 'frame-card error-card';
    card.innerHTML = `
        <div class="frame-thumb-wrap error-thumb">
            <span>分析失败</span>
        </div>
        <div class="frame-time">${event.capture_time}s</div>
        <div class="frame-metrics"><div class="fm-row"><span class="fm-val" style="color:var(--red);font-size:.75em;">${event.message}</span></div></div>`;
    document.getElementById('s-timeline').appendChild(card);
}

// ===== 最终结果 =====
let finalResult = null;

function showFinalResult(r) {
    finalResult = {
        is_changed: r.is_changed,
        change_time: r.change_time,
        deltaE: r.deltaE,
        deltaE_ratio: r.deltaE_ratio,
        change_ratio: r.change_ratio
    };
    const cards = [
        { ch: 'ΔE', cls: 'rc-ch-de', label: '色度差', value: r.deltaE.toFixed(2) },
        { ch: '%',  cls: 'rc-ch-pct', label: 'ΔE 占阈值比', value: (r.deltaE_ratio * 100).toFixed(1) + '%' },
        { ch: '格', cls: 'rc-ch-r',  label: '变色网格占比', value: (r.change_ratio * 100).toFixed(1) + '%' },
        { ch: 'T',  cls: '',          label: '变色时长', value: r.change_time + 's' }
    ];
    document.getElementById('s-final-cards').innerHTML = cards.map(c => `
        <div class="result-card${c.cls === 'rc-ch-de' ? ' result-card-accent' : ''}">
            <div class="rc-header">
                <span class="rc-ch mono ${c.cls}">${c.ch}</span>
                <span class="rc-label">${c.label}</span>
            </div>
            <div class="rc-value rc-value-large mono">${c.value}</div>
        </div>`).join('');
    document.getElementById('s-final').style.display = 'block';
    const inlineBtn = document.getElementById('s-view-result-btn-inline');
    inlineBtn.style.display = 'inline-block';
    inlineBtn.onclick = openResultModal;
}

function openResultModal() {
    if (!finalResult) return;
    document.getElementById('result-json-content').textContent = JSON.stringify(finalResult, null, 2);
    document.getElementById('result-modal').style.display = 'flex';
}

function closeResultModal() {
    document.getElementById('result-modal').style.display = 'none';
}

// ===== 详情 Modal =====
async function openModal(frameIndex) {
    if (!currentSessionId) return;
    try {
        const res = await fetch(`${STREAM_API}/frame/${currentSessionId}/${frameIndex}`);
        const data = await res.json();
        if (!data.success) return;

        modalAnalysisResult = data.analysis;
        document.getElementById('modal-title').textContent = `帧 #${frameIndex} 详情`;
        buildModalStepper(data.analysis.steps);
        showModalStep(0);
        buildModalResultCards(data.analysis.final_results);
        document.getElementById('detail-modal').style.display = 'flex';
    } catch (e) {
        showToast('加载详情失败: ' + e.message, 'error');
    }
}

function closeModal() {
    document.getElementById('detail-modal').style.display = 'none';
    modalAnalysisResult = null;
}

function buildModalStepper(steps) {
    const stepper = document.getElementById('modal-stepper');
    stepper.innerHTML = '';
    const validSteps = STREAM_STEP_KEYS.filter(k => steps[k]);
    window._modalStepKeys = validSteps;

    validSteps.forEach((key, i) => {
        const step = steps[key];
        const node = document.createElement('div');
        node.className = 'step-node';
        node.dataset.index = i;
        node.innerHTML = `
            <div class="step-dot-wrap">
                <div class="step-dot" id="mdot-${i}">${i + 1}</div>
                <div class="step-label">${step.title}</div>
            </div>`;
        node.addEventListener('click', () => showModalStep(i));
        stepper.appendChild(node);
        if (i < validSteps.length - 1) {
            const conn = document.createElement('div');
            conn.className = 'step-connector';
            conn.id = `mconn-${i}`;
            stepper.appendChild(conn);
        }
    });
}

function showModalStep(index) {
    modalActiveStep = index;
    const steps = modalAnalysisResult.steps;
    const keys = window._modalStepKeys || STREAM_STEP_KEYS;

    keys.forEach((_, i) => {
        const dot = document.getElementById(`mdot-${i}`);
        if (!dot) return;
        dot.className = 'step-dot' + (i < index ? ' done' : i === index ? ' active' : '');
        dot.closest('.step-node').className = 'step-node' + (i === index ? ' active' : i < index ? ' done' : '');
        const conn = document.getElementById(`mconn-${i}`);
        if (conn) conn.className = 'step-connector' + (i < index ? ' done' : '');
    });

    const step = steps[keys[index]];
    if (!step) return;

    const imagesHtml = Object.entries(step.images).map(([key, b64]) => `
        <div class="step-img-wrap">
            <img src="data:image/png;base64,${b64}" alt="${STREAM_IMG_LABELS[key] || key}">
            <div class="step-img-label">${STREAM_IMG_LABELS[key] || key}</div>
        </div>`).join('');

    const prevBtn = index > 0 ? `<button class="step-nav-btn" onclick="showModalStep(${index - 1})">← 上一步</button>` : '';
    const nextBtn = index < keys.length - 1 ? `<button class="step-nav-btn primary" onclick="showModalStep(${index + 1})">下一步 →</button>` : '';

    document.getElementById('modal-step-content').innerHTML = `
        <div class="step-content-inner">
            <div class="step-content-header"><h3>${step.title}</h3><p>${step.description}</p></div>
            ${imagesHtml ? `<div class="step-images">${imagesHtml}</div>` : ''}
            <div class="step-nav">${prevBtn}${nextBtn}</div>
        </div>`;
}

function buildModalResultCards(r) {
    const fmtLab = arr => `L ${arr[0]}  a ${arr[1]}  b ${arr[2]}`;
    document.getElementById('modal-result-cards').innerHTML = `
        <div class="result-card">
            <div class="rc-header"><span class="rc-ch mono">L</span><span class="rc-label">左侧基准 LAB</span></div>
            <div class="rc-value mono">${fmtLab(r.left_lab)}</div>
        </div>
        <div class="result-card">
            <div class="rc-header"><span class="rc-ch mono rc-ch-r">R</span><span class="rc-label">右侧平均 LAB</span></div>
            <div class="rc-value mono">${fmtLab(r.right_lab)}</div>
        </div>
        <div class="result-card result-card-accent">
            <div class="rc-header"><span class="rc-ch mono rc-ch-de">ΔE</span><span class="rc-label">整体色差</span></div>
            <div class="rc-value rc-value-large mono">${r.overall_delta_e.toFixed(2)}</div>
        </div>
        <div class="result-card">
            <div class="rc-header"><span class="rc-ch mono rc-ch-pct">%</span><span class="rc-label">超阈值网格</span></div>
            <div class="rc-value rc-value-large mono">${(r.color_change_ratio * 100).toFixed(1)}%</div>
        </div>`;
}
