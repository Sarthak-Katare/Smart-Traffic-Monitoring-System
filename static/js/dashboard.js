/**
 * Smart Traffic Optimization AI System — Dashboard JavaScript
 * 4-Lane Multi-Camera & Dynamic Wait Time Optimization Engine
 */

document.addEventListener('DOMContentLoaded', () => {
    console.log('[TRAFFIC AI] 4-Lane Multi-Camera Dashboard Initialized');

    // ── DOM References ─────────────────────────────────────────────────────
    const systemStatusPill   = document.getElementById('systemStatusPill');
    const statusText         = document.getElementById('statusText');
    const btnToggleProcess   = document.getElementById('btnToggleProcess');
    const btnRestartStreams  = document.getElementById('btnRestartStreams');
    const videoStreamImg     = document.getElementById('videoStreamImg');
    const videoPlaceholder   = document.getElementById('videoPlaceholder');
    const videoError         = document.getElementById('videoError');
    const videoErrorMessage  = document.getElementById('videoErrorMessage');
    const feedBadge          = document.getElementById('feedBadge');
    const viewIndicator      = document.getElementById('viewIndicator');
    const currentViewLabel   = document.getElementById('currentViewLabel');
    const cameraTabs         = document.querySelectorAll('.cam-tab');

    // Signal Controller DOM References
    const currentGreenLaneEl = document.getElementById('currentGreenLane');
    const timerCountdownEl   = document.getElementById('timerCountdown');
    const activePhaseStatus  = document.getElementById('activePhaseStatus');

    // Emergency Override References
    const overrideLaneSelect = document.getElementById('overrideLaneSelect');
    const btnForceGreen      = document.getElementById('btnForceGreen');
    const btnReleaseOverride = document.getElementById('btnReleaseOverride');

    // Modal References
    const btnOpenVideoManager= document.getElementById('btnOpenVideoManager');
    const videoManagerModal  = document.getElementById('videoManagerModal');
    const btnCloseModal      = document.getElementById('btnCloseModal');
    const btnModalClose      = document.getElementById('btnModalClose');
    const modalSourceList    = document.getElementById('modalSourceList');
    const toastContainer     = document.getElementById('toastContainer');

    // ── State ──────────────────────────────────────────────────────────────
    let isStreamActive = true;
    let currentCameraView = 'combined'; // 'combined', 'North', 'East', 'South', 'West'
    const LANES = ['North', 'East', 'South', 'West'];

    // ── Charts ─────────────────────────────────────────────────────────────
    let vehicleChart = null;
    let waitTimeChart = null;
    initCharts();

    // ── Health & Stats Polling ─────────────────────────────────────────────
    checkHealth();
    setInterval(checkHealth, 3000);

    // Poll stats every 1 second continuously
    pollStats();
    setInterval(pollStats, 1000);

    // ── NEW: Alert badge + toast polling every 5 seconds ──
    pollAlertBadge();
    setInterval(pollAlertBadge, 5000);

    // ══════════════════════════════════════════════════════════════════════
    //  Camera View Switcher Tabs (Quad vs Single Lane)
    // ══════════════════════════════════════════════════════════════════════

    cameraTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            cameraTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const view = tab.dataset.view;
            switchCameraView(view);
        });
    });

    // Expand buttons on individual lane boxes
    document.querySelectorAll('.view-cam-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const lane = btn.dataset.lane;
            cameraTabs.forEach(t => {
                if (t.dataset.view === lane) t.classList.add('active');
                else t.classList.remove('active');
            });
            switchCameraView(lane);
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    });

    function switchCameraView(view) {
        currentCameraView = view;
        if (!isStreamActive) return;

        if (view === 'combined') {
            videoStreamImg.src = '/video_feed/combined?' + Date.now();
            currentViewLabel.innerText = 'QUAD-VIEW (North, East, South, West)';
        } else {
            videoStreamImg.src = `/video_feed/${view}?` + Date.now();
            currentViewLabel.innerText = `${view.toUpperCase()} LANE CAMERA FEED`;
        }
    }

    // ══════════════════════════════════════════════════════════════════════
    //  START / STOP / RESTART Stream Handlers
    // ══════════════════════════════════════════════════════════════════════

    btnToggleProcess.addEventListener('click', async () => {
        if (isStreamActive) {
            await stopStreams();
        } else {
            await startStreams();
        }
    });

    btnRestartStreams.addEventListener('click', async () => {
        showToast('Restarting all 4 video streams...');
        await stopStreams();
        setTimeout(startStreams, 500);
    });

    async function startStreams() {
        btnToggleProcess.disabled = true;
        btnToggleProcess.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Starting...';

        try {
            const response = await fetch('/api/video/start', { method: 'POST' });
            const data = await response.json();

            if (data.success) {
                isStreamActive = true;
                videoPlaceholder.style.display = 'none';
                videoError.style.display = 'none';
                videoStreamImg.style.display = 'block';

                switchCameraView(currentCameraView);

                btnToggleProcess.innerHTML = '<i class="fa-solid fa-square"></i> Stop Stream';
                btnToggleProcess.className = 'btn btn-danger';
                feedBadge.innerHTML = '<i class="fa-solid fa-circle" style="color:#34c759"></i> Cameras Live';
                showToast('All 4 video camera feeds started.');
            } else {
                showVideoError(data.message);
            }
        } catch (err) {
            showVideoError('Could not connect to server.');
        }

        btnToggleProcess.disabled = false;
    }

    async function stopStreams() {
        try {
            await fetch('/api/video/stop', { method: 'POST' });
        } catch (_) {}

        isStreamActive = false;
        videoStreamImg.src = '';
        videoStreamImg.style.display = 'none';
        videoPlaceholder.style.display = 'flex';

        btnToggleProcess.innerHTML = '<i class="fa-solid fa-play"></i> Start AI Stream';
        btnToggleProcess.className = 'btn btn-primary';
        feedBadge.innerHTML = '<i class="fa-solid fa-circle" style="color:#f59e0b"></i> Suspended';
        showToast('Camera feeds stopped.');
    }

    function showVideoError(msg) {
        videoPlaceholder.style.display = 'none';
        videoStreamImg.style.display = 'none';
        videoError.style.display = 'flex';
        videoErrorMessage.innerText = msg;
        btnToggleProcess.innerHTML = '<i class="fa-solid fa-play"></i> Start AI Stream';
        btnToggleProcess.className = 'btn btn-primary';
        isStreamActive = false;
    }

    // ══════════════════════════════════════════════════════════════════════
    //  Live Stats & Signal / Wait Time Controller Polling
    // ══════════════════════════════════════════════════════════════════════

    async function pollStats() {
        try {
            const response = await fetch('/api/stats');
            if (!response.ok) return;
            const data = await response.json();

            const b = data.breakdown || {};

            // 1. Update vehicle count stat cards
            animateCount(document.getElementById('statTotalVehicles'), data.total_vehicles || 0);
            animateCount(document.getElementById('statCars'),          b.cars || 0);
            animateCount(document.getElementById('statBikes'),         b.motorcycles || 0);
            animateCount(document.getElementById('statBuses'),         b.buses || 0);
            animateCount(document.getElementById('statTrucks'),        b.trucks || 0);

            // 2. Update Vehicle Distribution Doughnut Chart
            if (vehicleChart) {
                vehicleChart.data.datasets[0].data = [
                    b.cars || 0,
                    b.motorcycles || 0,
                    b.buses || 0,
                    b.trucks || 0
                ];
                vehicleChart.update('none');
            }

            // 3. Update Active Green Banner & Status
            if (currentGreenLaneEl) {
                currentGreenLaneEl.innerText = (data.active_green_lane || 'NORTH').toUpperCase();
            }
            if (timerCountdownEl) {
                timerCountdownEl.innerText = data.remaining_seconds;
            }
            if (activePhaseStatus) {
                if (data.override_active) {
                    activePhaseStatus.innerText = `EMERGENCY OVERRIDE (${data.override_lane} Forced Green)`;
                } else if (data.active_state === 'YELLOW') {
                    activePhaseStatus.innerText = 'Yellow Caution Light Active (Clearing)';
                    timerCountdownEl.style.color = 'var(--accent-amber)';
                } else {
                    activePhaseStatus.innerText = 'Green Light Remaining (Dynamic AI)';
                    timerCountdownEl.style.color = 'var(--signal-green)';
                }
            }

            // 4. Update Emergency Override UI State
            if (data.override_active) {
                btnForceGreen.style.display = 'none';
                btnReleaseOverride.style.display = 'inline-flex';
            } else {
                btnForceGreen.style.display = 'inline-flex';
                btnReleaseOverride.style.display = 'none';
            }

            // 5. Update Per-Lane Signals, Dynamic Wait Times & Density Cards
            const lanes = data.lanes || {};
            const waitTimeValues = [];
            const vehicleCounts = [];

            LANES.forEach(laneName => {
                const lData = lanes[laneName];
                if (!lData) return;

                waitTimeValues.push(lData.wait_time);
                vehicleCounts.push(lData.count);

                // --- Update Signal Light Card ---
                const sigCard = document.getElementById(`signalCard-${laneName}`);
                if (sigCard) {
                    const redBulb    = sigCard.querySelector('.light.red');
                    const yellowBulb = sigCard.querySelector('.light.yellow');
                    const greenBulb  = sigCard.querySelector('.light.green');
                    const badge      = document.getElementById(`signalBadge-${laneName}`);
                    const waitValEl  = document.getElementById(`waitVal-${laneName}`);
                    const sigCountEl = document.getElementById(`sigCount-${laneName}`);
                    const sigPcuEl   = document.getElementById(`sigPcu-${laneName}`);
                    const sigGreenEl = document.getElementById(`sigGreen-${laneName}`);
                    const queueTagEl = document.getElementById(`queueTag-${laneName}`);

                    // Reset bulbs
                    if (redBulb)    redBulb.classList.remove('active');
                    if (yellowBulb) yellowBulb.classList.remove('active');
                    if (greenBulb)  greenBulb.classList.remove('active');
                    sigCard.classList.remove('active-green', 'active-yellow');

                    if (sigCountEl) sigCountEl.innerText = `${lData.count} vehicles`;
                    if (sigPcuEl)   sigPcuEl.innerText = `${lData.pcu_score} PCU (${lData.density})`;
                    if (sigGreenEl) sigGreenEl.innerText = `${lData.green_time}s`;

                    if (lData.status === 'GREEN') {
                        if (greenBulb) greenBulb.classList.add('active');
                        sigCard.classList.add('active-green');
                        if (badge) {
                            badge.innerText = 'ACTIVE GREEN';
                            badge.className = 'status-badge';
                        }
                        if (waitValEl) {
                            waitValEl.innerText = '0s (Discharging)';
                            waitValEl.className = 'wait-value active';
                        }
                        if (queueTagEl) {
                            queueTagEl.innerHTML = '<i class="fa-solid fa-circle-check" style="color:#34c759"></i> Actively Flowing';
                        }
                    } else if (lData.status === 'YELLOW') {
                        if (yellowBulb) yellowBulb.classList.add('active');
                        sigCard.classList.add('active-yellow');
                        if (badge) {
                            badge.innerText = 'CAUTION';
                            badge.className = 'status-badge yellow';
                        }
                        if (waitValEl) {
                            waitValEl.innerText = `${data.remaining_seconds}s Caution`;
                            waitValEl.className = 'wait-value';
                        }
                        if (queueTagEl) {
                            queueTagEl.innerHTML = '<i class="fa-solid fa-triangle-exclamation" style="color:#f59e0b"></i> Transitioning to Red';
                        }
                    } else {
                        // RED WAITING
                        if (redBulb) redBulb.classList.add('active');
                        if (badge) {
                            badge.innerText = 'WAITING (RED)';
                            badge.className = 'status-badge red';
                        }
                        if (waitValEl) {
                            waitValEl.innerText = `${lData.wait_time}s`;
                            waitValEl.className = 'wait-value';
                        }
                        if (queueTagEl) {
                            const pos = lData.queue_position;
                            const posText = pos === 1 ? 'Queue #1 (Next in line)' : `Queue #${pos}`;
                            queueTagEl.innerHTML = `<i class="fa-solid fa-clock"></i> ${posText}`;
                        }
                    }
                }

                // --- Update Density Breakdown Box ---
                const elCount = document.getElementById(`count-${laneName}`);
                if (elCount) animateCount(elCount, lData.count);

                const elPcu = document.getElementById(`pcu-${laneName}`);
                if (elPcu) elPcu.innerText = `${lData.pcu_score} PCU`;

                const elBoxWait = document.getElementById(`boxWait-${laneName}`);
                if (elBoxWait) {
                    if (lData.status === 'GREEN') {
                        elBoxWait.innerText = '0s (Green)';
                        elBoxWait.className = 'text-emerald';
                    } else {
                        elBoxWait.innerText = `${lData.wait_time}s`;
                        elBoxWait.className = 'text-amber';
                    }
                }

                const elRecGreen = document.getElementById(`recGreen-${laneName}`);
                if (elRecGreen) elRecGreen.innerText = `${lData.green_time}s`;

                const elBadge = document.getElementById(`density-${laneName}`);
                if (elBadge) {
                    const level = lData.density;
                    elBadge.innerText = level;
                    elBadge.className = `density-badge ${level.toLowerCase()}`;
                }
            });

            // 6. Update Real-Time Wait Time & Count Chart
            if (waitTimeChart && waitTimeValues.length === 4) {
                waitTimeChart.data.datasets[0].data = waitTimeValues;
                waitTimeChart.data.datasets[1].data = vehicleCounts;
                waitTimeChart.update('none');
            }

            // 7. Update Video File Sources if available
            if (data.video_status && data.video_status.lanes) {
                LANES.forEach(laneName => {
                    const info = data.video_status.lanes[laneName];
                    if (info && info.source) {
                        const sLabel = document.getElementById(`sourceLabel-${laneName}`);
                        if (sLabel) sLabel.innerText = info.source;
                        const bSource = document.getElementById(`boxSource-${laneName}`);
                        if (bSource) bSource.innerText = info.source;
                    }
                });
            }

        } catch (err) {
            // Silently swallow tick network hiccups
        }
    }

    function animateCount(el, newVal) {
        if (!el) return;
        const current = parseInt(el.innerText) || 0;
        if (current === newVal) return;
        el.innerText = newVal;
        el.style.color = '#06b6d4';
        setTimeout(() => { el.style.color = ''; }, 400);
    }

    // ══════════════════════════════════════════════════════════════════════
    //  Emergency Override Controls
    // ══════════════════════════════════════════════════════════════════════

    btnForceGreen.addEventListener('click', async () => {
        const lane = overrideLaneSelect.value;
        try {
            const res = await fetch('/api/signal/override', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'enable', lane, duration: 30 })
            });
            const data = await res.json();
            if (data.success) {
                showToast(`🚨 Priority Forced: ${lane} Lane GREEN for 30s!`);
                pollStats();
            }
        } catch (err) {
            showToast('Failed to trigger override.');
        }
    });

    btnReleaseOverride.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/signal/override', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'disable' })
            });
            const data = await res.json();
            if (data.success) {
                showToast('Emergency override released. AI Dynamic Mode resumed.');
                pollStats();
            }
        } catch (err) {
            showToast('Failed to release override.');
        }
    });

    // ══════════════════════════════════════════════════════════════════════
    //  Per-Lane Video Upload Handlers
    // ══════════════════════════════════════════════════════════════════════

    document.querySelectorAll('.lane-file-input').forEach(input => {
        input.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            const lane = input.dataset.lane;
            const formData = new FormData();
            formData.append('video_file', file);

            showToast(`Uploading video for ${lane} Lane...`);

            try {
                const response = await fetch(`/api/video/upload/${lane}`, {
                    method: 'POST',
                    body: formData
                });
                const data = await response.json();

                if (data.success) {
                    showToast(`✅ Video for ${lane} Lane updated: ${data.filename}`);
                    if (currentCameraView === lane || currentCameraView === 'combined') {
                        switchCameraView(currentCameraView);
                    }
                } else {
                    showToast(`❌ Upload failed: ${data.message}`);
                }
            } catch (err) {
                showToast('Upload error. Please check file size.');
            }
        });
    });

    // ══════════════════════════════════════════════════════════════════════
    //  4-Lane Video Manager Modal
    // ══════════════════════════════════════════════════════════════════════

    btnOpenVideoManager.addEventListener('click', openVideoManagerModal);
    btnCloseModal.addEventListener('click', () => { videoManagerModal.style.display = 'none'; });
    btnModalClose.addEventListener('click', () => { videoManagerModal.style.display = 'none'; });
    videoManagerModal.addEventListener('click', (e) => {
        if (e.target === videoManagerModal) videoManagerModal.style.display = 'none';
    });

    function fetchWithTimeout(url, ms = 2500) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), ms);
        return fetch(url, { signal: controller.signal })
            .then(r => r.json())
            .catch(() => ({}))
            .finally(() => clearTimeout(timer));
    }

    async function openVideoManagerModal() {
        videoManagerModal.style.display = 'flex';
        modalSourceList.innerHTML = '<p><i class="fa-solid fa-spinner fa-spin"></i> Loading video sources...</p>';

        try {
            const [resFiles, resWebcams, resStatus] = await Promise.all([
                fetchWithTimeout('/api/video/list_files'),
                fetchWithTimeout('/api/video/list_webcams'),
                fetchWithTimeout('/api/video/status')
            ]);

            const files = (resFiles && resFiles.files) || [
                { name: 'lane_north.mp4' },
                { name: 'lane_east.mp4' },
                { name: 'lane_south.mp4' },
                { name: 'lane_west.mp4' },
                { name: 'traffic.mp4' }
            ];
            const webcams = (resWebcams && resWebcams.webcams && resWebcams.webcams.length > 0)
                ? resWebcams.webcams
                : [
                    { index: 0, name: 'Camera 0 (Default / Laptop Webcam)' },
                    { index: 1, name: 'Camera 1 (External USB Camera)' }
                ];
            const laneStatus = (resStatus && resStatus.lanes) || {};

            let html = '';

            LANES.forEach(lane => {
                const info = laneStatus[lane] || {};
                const cur = info.source || ('lane_' + lane.toLowerCase() + '.mp4');
                const isLive = Boolean(info.is_live);
                const isCustomUrl = cur.startsWith('http://') || cur.startsWith('https://') || cur.startsWith('rtsp://');

                html += `
                <div class="source-item" data-lane="${lane}">
                    <div class="source-item-top">
                        <span class="source-item-lane">
                            <i class="fa-solid fa-video"></i> ${lane} Lane Camera
                            <span class="live-badge-indicator ${isLive ? 'live' : 'file'}">
                                <i class="fa-solid ${isLive ? 'fa-tower-broadcast' : 'fa-film'}"></i>
                                ${isLive ? 'LIVE' : 'FILE'}
                            </span>
                        </span>
                        <span class="source-item-current" title="${cur}">Active: ${cur}</span>
                    </div>

                    <div class="source-item-controls">
                        <select class="custom-select-sm lane-source-mode" data-lane="${lane}">
                            <optgroup label="📁 Video Files">
                                ${files.map(f => `<option value="${f.name}" ${(!isLive && !isCustomUrl && f.name === cur) ? 'selected' : ''}>${f.name}</option>`).join('')}
                            </optgroup>
                            <optgroup label="📹 Live Webcams">
                                ${webcams.length > 0 
                                    ? webcams.map(w => `<option value="${w.index}" ${(cur === `Webcam ${w.index}` || cur === String(w.index)) ? 'selected' : ''}>${w.name}</option>`).join('')
                                    : `<option value="0" ${cur === 'Webcam 0' || cur === '0' ? 'selected' : ''}>Camera 0 (Default Webcam)</option>`
                                }
                            </optgroup>
                            <optgroup label="🌐 Live Network Stream">
                                <option value="__custom__" ${isCustomUrl ? 'selected' : ''}>Custom RTSP / HTTP URL...</option>
                            </optgroup>
                        </select>

                        <input type="text" 
                               class="source-custom-input lane-custom-url" 
                               data-lane="${lane}" 
                               placeholder="e.g. http://192.168.1.50:8080/video or rtsp://..." 
                               value="${isCustomUrl ? cur : ''}"
                               style="display: ${isCustomUrl ? 'block' : 'none'};">

                        <button class="btn btn-outline-sm btn-apply-source" data-lane="${lane}">
                            <i class="fa-solid fa-check"></i> Apply
                        </button>
                    </div>
                </div>`;
            });

            // Add real-time live streaming guide
            html += `
            <div class="realtime-guide-card">
                <h4><i class="fa-solid fa-lightbulb"></i> How to Ingest Real-Time Live Feeds:</h4>
                <ul style="margin: 0; padding-left: 1.2rem; display: flex; flex-direction: column; gap: 4px;">
                    <li><strong>Built-in / USB Webcam:</strong> Select <code>Camera 0</code> to stream from your laptop webcam directly in real-time.</li>
                    <li><strong>Phone as Live Traffic Camera:</strong> Install free <em>IP Webcam</em> (Android) or <em>DroidCam</em>, start server, select <em>Custom URL</em> and enter <code>http://&lt;phone-ip&gt;:8080/video</code>.</li>
                    <li><strong>Physical CCTV / NVR:</strong> Select <em>Custom URL</em> and enter standard RTSP link e.g. <code>rtsp://username:password@&lt;ip&gt;:554/stream1</code>.</li>
                </ul>
            </div>`;

            modalSourceList.innerHTML = html;

            // Handle dropdown change to show/hide custom URL input
            modalSourceList.querySelectorAll('.lane-source-mode').forEach(sel => {
                sel.addEventListener('change', () => {
                    const lane = sel.dataset.lane;
                    const urlInput = modalSourceList.querySelector(`.lane-custom-url[data-lane="${lane}"]`);
                    if (sel.value === '__custom__') {
                        urlInput.style.display = 'block';
                        urlInput.focus();
                    } else {
                        urlInput.style.display = 'none';
                    }
                });
            });

            // Attach apply handlers
            modalSourceList.querySelectorAll('.btn-apply-source').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const lane = btn.dataset.lane;
                    const modeSel = modalSourceList.querySelector(`.lane-source-mode[data-lane="${lane}"]`);
                    const urlInput = modalSourceList.querySelector(`.lane-custom-url[data-lane="${lane}"]`);
                    
                    let sourceVal = modeSel.value;
                    if (sourceVal === '__custom__') {
                        sourceVal = (urlInput.value || '').trim();
                        if (!sourceVal) {
                            showToast('Please enter an RTSP or HTTP stream URL.');
                            urlInput.focus();
                            return;
                        }
                    }

                    btn.disabled = true;
                    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';

                    try {
                        const res = await fetch('/api/video/set_source', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ lane, source: sourceVal })
                        });
                        const resData = await res.json();
                        if (resData.success) {
                            showToast(`✅ ${lane} source set to: ${sourceVal}`);
                            openVideoManagerModal();
                            if (currentCameraView === lane || currentCameraView === 'combined') {
                                switchCameraView(currentCameraView);
                            }
                        } else {
                            showToast(`❌ Error: ${resData.message}`);
                            btn.disabled = false;
                            btn.innerHTML = '<i class="fa-solid fa-check"></i> Apply';
                        }
                    } catch (err) {
                        showToast('Failed to connect to video source.');
                        btn.disabled = false;
                        btn.innerHTML = '<i class="fa-solid fa-check"></i> Apply';
                    }
                });
            });

        } catch (err) {
            modalSourceList.innerHTML = '<p class="text-danger">Failed to load video source manager.</p>';
        }
    }

    // ══════════════════════════════════════════════════════════════════════
    //  Health Check / Status Polling
    // ══════════════════════════════════════════════════════════════════════

    async function checkHealth() {
        try {
            const response = await fetch('/api/status');
            if (response.ok) {
                const data = await response.json();
                const yoloOk = data.detector?.model_loaded;
                statusText.innerText = yoloOk
                    ? `Online | 4-Lane YOLO (${data.system_config.yolo_model})`
                    : `Online (YOLO initializing...)`;
                systemStatusPill.style.borderColor = 'rgba(16,185,129,0.5)';
                systemStatusPill.style.color       = 'var(--accent-emerald)';
            }
        } catch (_) {
            statusText.innerText               = 'Server Offline';
            systemStatusPill.style.borderColor = 'rgba(239,68,68,0.5)';
            systemStatusPill.style.color       = '#ef4444';
        }
    }

    // ══════════════════════════════════════════════════════════════════════
    //  Toast Notifications Helper
    // ══════════════════════════════════════════════════════════════════════

    function showToast(message) {
        if (!toastContainer) return;
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.innerHTML = `<i class="fa-solid fa-circle-info" style="color:var(--accent-cyan)"></i> <span>${message}</span>`;
        toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(10px)';
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    }

    // ══════════════════════════════════════════════════════════════════════
    //  Chart.js Initialization
    // ══════════════════════════════════════════════════════════════════════

    function initCharts() {
        const ctxVehicle  = document.getElementById('vehicleDistributionChart')?.getContext('2d');
        const ctxWaitTime = document.getElementById('laneWaitTimeChart')?.getContext('2d');

        if (ctxVehicle) {
            vehicleChart = new Chart(ctxVehicle, {
                type: 'doughnut',
                data: {
                    labels: ['Cars (1.0 PCU)', 'Motorcycles (0.5)', 'Buses (2.5)', 'Trucks (3.0)'],
                    datasets: [{
                        data: [0, 0, 0, 0],
                        backgroundColor: ['#ff7832', '#32dc64', '#32c8ff', '#ff3c3c'],
                        borderWidth: 0,
                        hoverOffset: 8
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '62%',
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: '#94a3b8', padding: 12, font: { family: 'Inter', size: 11 } }
                        },
                        title: {
                            display: true,
                            text: 'Vehicle Type Distribution (4 Lanes)',
                            color: '#f8fafc',
                            font: { family: 'Inter', size: 13, weight: '700' }
                        }
                    }
                }
            });
        }

        if (ctxWaitTime) {
            waitTimeChart = new Chart(ctxWaitTime, {
                type: 'bar',
                data: {
                    labels: ['North Lane', 'East Lane', 'South Lane', 'West Lane'],
                    datasets: [
                        {
                            label: 'Dynamic Wait Time (sec)',
                            data: [0, 18, 36, 54],
                            backgroundColor: 'rgba(245, 158, 11, 0.85)',
                            borderRadius: 6,
                            yAxisID: 'y'
                        },
                        {
                            label: 'Vehicles Detected',
                            data: [0, 0, 0, 0],
                            backgroundColor: 'rgba(6, 182, 212, 0.85)',
                            borderRadius: 6,
                            yAxisID: 'y1'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } }
                        },
                        title: {
                            display: true,
                            text: 'Dynamic Wait Time vs. Vehicle Queue per Lane',
                            color: '#f8fafc',
                            font: { family: 'Inter', size: 13, weight: '700' }
                        }
                    },
                    scales: {
                        x: {
                            ticks: { color: '#94a3b8', font: { family: 'Inter' } },
                            grid: { color: '#1e293b' }
                        },
                        y: {
                            type: 'linear',
                            display: true,
                            position: 'left',
                            title: { display: true, text: 'Wait Time (s)', color: '#f59e0b', font: { size: 10 } },
                            ticks: { color: '#94a3b8', font: { family: 'Inter' } },
                            grid: { color: '#1e293b' },
                            beginAtZero: true
                        },
                        y1: {
                            type: 'linear',
                            display: true,
                            position: 'right',
                            title: { display: true, text: 'Vehicle Count', color: '#06b6d4', font: { size: 10 } },
                            ticks: { color: '#94a3b8', font: { family: 'Inter' } },
                            grid: { drawOnChartArea: false },
                            beginAtZero: true
                        }
                    }
                }
            });
        }
    }

    // ══════════════════════════════════════════════════════════════════════
    //  VAHAN Vehicle RC Verification & ANPR Handlers
    // ══════════════════════════════════════════════════════════════════════

    const vahanPlateInput   = document.getElementById('vahanPlateInput');
    const btnVerifyPlate    = document.getElementById('btnVerifyPlate');
    const btnAnprScan       = document.getElementById('btnAnprScan');
    const platePills        = document.querySelectorAll('.plate-pill');

    if (btnVerifyPlate) {
        btnVerifyPlate.addEventListener('click', () => {
            const plate = vahanPlateInput.value.trim();
            if (plate) verifyVehiclePlate(plate);
            else showToast('Please enter a vehicle registration number.');
        });
    }

    if (vahanPlateInput) {
        vahanPlateInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                const plate = vahanPlateInput.value.trim();
                if (plate) verifyVehiclePlate(plate);
            }
        });
    }

    platePills.forEach(pill => {
        pill.addEventListener('click', () => {
            const plate = pill.dataset.plate;
            if (vahanPlateInput) vahanPlateInput.value = plate;
            verifyVehiclePlate(plate);
        });
    });

    if (btnAnprScan) {
        btnAnprScan.addEventListener('click', async () => {
            btnAnprScan.disabled = true;
            btnAnprScan.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Scanning...';
            showToast('Scanning active camera stream for license plates...');

            try {
                const res = await fetch('/api/vahan/anpr_scan', { method: 'POST' });
                const result = await res.json();
                if (result.success && result.data) {
                    renderVahanCard(result.data);
                    if (vahanPlateInput) vahanPlateInput.value = result.data.registration_no;
                    showToast(`📷 ANPR Scan: Detected ${result.data.registration_no} on ${result.camera_source}`);
                }
            } catch (_) {
                showToast('ANPR camera scan failed.');
            }

            btnAnprScan.disabled = false;
            btnAnprScan.innerHTML = '<i class="fa-solid fa-camera"></i> Scan Camera ANPR';
        });
    }

    async function verifyVehiclePlate(plate) {
        if (!btnVerifyPlate) return;
        btnVerifyPlate.disabled = true;
        btnVerifyPlate.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Verifying...';

        try {
            const res = await fetch('/api/vahan/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ registration_number: plate })
            });
            const result = await res.json();

            if (result.success && result.data) {
                renderVahanCard(result.data);
                showToast(`✅ VAHAN Verified: ${result.data.registration_no} (${result.data.maker_model})`);
            } else {
                showToast(`❌ ${result.message || 'Verification failed.'}`);
            }
        } catch (err) {
            showToast('Server error while querying VAHAN database.');
        }

        btnVerifyPlate.disabled = false;
        btnVerifyPlate.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> Verify RC';
    }

    function renderVahanCard(data) {
        const elPlate     = document.getElementById('vahanCardPlate');
        const elModel     = document.getElementById('vahanCardModel');
        const elClass     = document.getElementById('vahanCardClass');
        const elFuel      = document.getElementById('vahanCardFuel');
        const elRto       = document.getElementById('vahanCardRto');
        const elOwner     = document.getElementById('vahanCardOwner');
        const elRegDate   = document.getElementById('vahanCardRegDate');
        const elFitness   = document.getElementById('vahanCardFitness');
        const elTax       = document.getElementById('vahanCardTax');
        const elInsStatus = document.getElementById('vahanCardInsuranceStatus');
        const elInsurer   = document.getElementById('vahanCardInsurer');
        const elPucStatus = document.getElementById('vahanCardPucStatus');
        const elEmission  = document.getElementById('vahanCardEmission');
        const elChallan   = document.getElementById('vahanCardChallanStatus');
        const elBlacklist = document.getElementById('vahanCardBlacklist');
        const elAnprConf  = document.getElementById('vahanCardAnprConf');
        const elChallanSum= document.getElementById('vahanChallanSummary');
        const elVerifyTime= document.getElementById('vahanVerifyTime');

        if (elPlate)   elPlate.innerText = data.registration_no;
        if (elModel)   elModel.innerText = data.maker_model;
        if (elClass)   elClass.innerText = data.vehicle_class;
        if (elFuel)    elFuel.innerText = `${data.fuel_type} (${data.emission_norms ? 'BS-VI' : ''})`;
        if (elRto)     elRto.innerText = data.rto_name;
        if (elOwner)   elOwner.innerText = data.owner_name;
        if (elRegDate) elRegDate.innerText = data.registration_date;
        if (elFitness) elFitness.innerText = data.fitness_upto;
        if (elTax)     elTax.innerText = data.tax_upto;
        if (elEmission)elEmission.innerText = data.emission_norms;
        if (elBlacklist) elBlacklist.innerText = data.blacklist_status;
        if (elAnprConf)  elAnprConf.innerText = `${data.anpr_confidence}%`;
        if (elVerifyTime)elVerifyTime.innerText = data.verified_at || 'Just now';

        // Insurance
        if (elInsStatus && data.insurance_details) {
            const ins = data.insurance_details;
            if (ins.is_active) {
                elInsStatus.className = 'status-chip active';
                elInsStatus.innerHTML = `<i class="fa-solid fa-circle-check"></i> ACTIVE (Till ${ins.valid_upto})`;
            } else {
                elInsStatus.className = 'status-chip expired';
                elInsStatus.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> EXPIRED (${ins.valid_upto})`;
            }
            if (elInsurer) elInsurer.innerText = ins.company;
        }

        // PUC
        if (elPucStatus && data.puc_details) {
            const puc = data.puc_details;
            if (puc.is_active) {
                elPucStatus.className = 'status-chip active';
                elPucStatus.innerHTML = `<i class="fa-solid fa-leaf"></i> VALID (${puc.valid_upto})`;
            } else {
                elPucStatus.className = 'status-chip expired';
                elPucStatus.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> EXPIRED (${puc.valid_upto})`;
            }
        }

        // Challans
        if (data.e_challan_summary) {
            const ch = data.e_challan_summary;
            if (elChallan) {
                if (ch.pending_count > 0) {
                    elChallan.className = 'text-amber';
                    elChallan.innerText = `${ch.pending_count} Pending (₹${ch.pending_amount})`;
                } else {
                    elChallan.className = 'text-emerald';
                    elChallan.innerText = '0 Pending (Clean)';
                }
            }
            if (elChallanSum) {
                if (ch.records && ch.records.length > 0) {
                    elChallanSum.innerHTML = ch.records.map(r => 
                        `<div><strong>${r.challan_no}</strong>: ${r.offense} — ₹${r.amount} (${r.status})</div>`
                    ).join('');
                } else {
                    elChallanSum.innerText = 'No unpaid traffic violations found on VAHAN registry.';
                }
            }
        }
    }


// ==========================================================================
// Alert Badge & Live Toast System — City-Wide Alert Integration
// ==========================================================================

let _lastAlertIdsOnDash = new Set();

function pollAlertBadge() {
    fetch('/api/alerts')
        .then(r => r.json())
        .then(data => {
            const summary = data.summary || {};
            const active  = summary.active || 0;

            // Update nav badge
            const badge = document.getElementById('navAlertBadge');
            if (badge) {
                badge.textContent = active;
                badge.style.display = active > 0 ? 'inline-flex' : 'none';
            }

            // Fire toast for any NEW alerts since last poll
            const alerts = data.alerts || [];
            alerts.forEach(a => {
                if (!_lastAlertIdsOnDash.has(a.id)) {
                    showAlertToast(a);
                }
            });
            _lastAlertIdsOnDash = new Set(alerts.map(a => a.id));
        })
        .catch(() => {});
}

function showAlertToast(alert) {
    const isCritical = alert.severity === 'CRITICAL';
    const color = isCritical ? '#ef4444' : '#f59e0b';
    const toast = document.createElement('div');
    toast.style.cssText = `
        position:fixed; bottom:28px; right:28px; z-index:99999;
        background:#0d1117; border:1px solid ${color}; border-left:4px solid ${color};
        border-radius:12px; padding:1rem 1.3rem;
        font-family:'Inter',sans-serif; color:#e2e8f0;
        box-shadow:0 4px 32px rgba(0,0,0,0.7);
        max-width:360px; min-width:280px;
        animation:toastIn 0.35s cubic-bezier(0.34,1.56,0.64,1);
        cursor:pointer;
    `;
    toast.innerHTML = `
        <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.35rem;">
            <i class="fa-solid fa-${isCritical ? 'siren-on' : 'triangle-exclamation'}"
               style="color:${color};font-size:0.95rem;"></i>
            <span style="font-weight:800;font-size:0.82rem;color:${color};">NEW ${alert.severity}</span>
            <span style="font-family:'JetBrains Mono',monospace;font-weight:700;font-size:0.82rem;margin-left:auto;"
                >${alert.plate}</span>
        </div>
        <div style="font-size:0.74rem;color:#94a3b8;line-height:1.4;">${alert.message}</div>
        <div style="font-size:0.65rem;color:#4b5563;margin-top:0.4rem;">
            ${alert.camera_id} Camera • ${alert.timestamp}
        </div>
    `;
    // Click to navigate to alerts page
    toast.addEventListener('click', () => window.location.href = '/alerts');
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.transition = 'opacity 0.5s, transform 0.5s';
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(30px)';
        setTimeout(() => toast.remove(), 550);
    }, 7000);
}

// Global helper for the Clear ANPR Log button in HTML
window.clearAnprLog = function() {
    const tbody = document.getElementById('anprLogBody');
    if (tbody) {
        tbody.innerHTML = `
            <tr class="anpr-empty-row">
                <td colspan="6">
                    <i class="fa-solid fa-satellite-dish"></i>
                    Log cleared. Waiting for ANPR engine to detect plates from live camera feeds...
                </td>
            </tr>`;
    }
};

}); // End of DOMContentLoaded
