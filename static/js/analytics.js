/**
 * analytics.js — City Traffic Analytics Dashboard
 * Renders heatmap, flow chart, OD matrix, speed estimates, congestion
 */

let heatmapMap   = null;
let heatLayer    = null;
let nodeMarkers  = [];
let flowChart    = null;

document.addEventListener('DOMContentLoaded', () => {
    initHeatmapMap();
    refreshAnalytics();
    updateAlertBadge();
    setInterval(updateAlertBadge, 10000);
    setInterval(refreshAnalytics, 30000); // Auto-refresh every 30s
});

// ── Heatmap Map Init ───────────────────────────────────────────────────────

function initHeatmapMap() {
    heatmapMap = L.map('heatmapContainer', {
        center: [28.6050, 77.1900],
        zoom: 11,
        zoomControl: true,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 18,
    }).addTo(heatmapMap);
}

// ── Main Data Load ─────────────────────────────────────────────────────────

function refreshAnalytics() {
    fetch('/api/analytics/dashboard')
        .then(r => r.json())
        .then(data => {
            renderHeatmap(data.heatmap, data.camera_nodes);
            renderFlowChart(data.flow_trends);
            renderODMatrix(data.od_matrix);
            renderSpeedCards(data.speed_estimates);
            renderCongestion(data.congestion);
            renderStatCards(data);
        })
        .catch(err => console.error('[Analytics] Fetch error:', err));
}

// ── KPI Stat Cards ─────────────────────────────────────────────────────────

function renderStatCards(data) {
    const flow = data.flow_trends;
    const speeds = data.speed_estimates;
    const congestion = data.congestion;

    document.getElementById('statTotal').textContent  = flow.total_vehicles || 0;
    document.getElementById('statPeak').textContent   = flow.peak_hour || 'N/A';
    document.getElementById('statPeakCount').textContent = flow.peak_count > 0
        ? `${flow.peak_count} vehicles at peak` : 'Busiest time slot';

    if (speeds && speeds.length > 0) {
        const avg = speeds.reduce((s, i) => s + i.avg_speed_kmh, 0) / speeds.length;
        document.getElementById('statSpeed').textContent = Math.round(avg) + ' km/h';
    } else {
        document.getElementById('statSpeed').textContent = '—';
    }

    document.getElementById('statCongestion').textContent = congestion ? congestion.length : 0;
}

// ── Heatmap ────────────────────────────────────────────────────────────────

function renderHeatmap(heatData, cameraNodes) {
    // Remove old heat layer & markers
    if (heatLayer) { heatmapMap.removeLayer(heatLayer); heatLayer = null; }
    nodeMarkers.forEach(m => heatmapMap.removeLayer(m));
    nodeMarkers = [];

    if (!heatData || heatData.length === 0) return;

    // Leaflet.heat format: [lat, lon, intensity]
    const points = heatData.map(p => [p.lat, p.lon, p.intensity]);
    heatLayer = L.heatLayer(points, {
        radius: 60,
        blur: 40,
        maxZoom: 15,
        gradient: { 0.2: '#4338ca', 0.5: '#7c3aed', 0.75: '#f59e0b', 1.0: '#ef4444' },
    }).addTo(heatmapMap);

    // Camera node markers
    (cameraNodes || heatData).forEach(node => {
        const cam = heatData.find(h => h.camera_id === node.id) || node;
        const icon = L.divIcon({
            className: '',
            html: `<div style="
                background:#1e2130; border:2px solid #818cf8;
                border-radius:8px; padding:4px 8px;
                font-family:'Inter',sans-serif; font-size:0.65rem;
                font-weight:700; color:#a5b4fc;
                white-space:nowrap; box-shadow:0 2px 12px rgba(0,0,0,0.5);
            ">${node.id || node.camera_id}: ${cam.count || 0}</div>`,
            iconSize: [80, 26],
            iconAnchor: [40, 26],
        });

        const lat = node.lat || cam.lat;
        const lon = node.lon || cam.lon;
        if (!lat || !lon) return;

        const marker = L.marker([lat, lon], { icon })
            .addTo(heatmapMap)
            .bindPopup(`
                <div style="font-family:'Inter',sans-serif;">
                    <b>${node.name || cam.name || node.id}</b><br>
                    <small>${node.zone || cam.city_zone || ''}</small><br>
                    <span style="color:#818cf8;font-weight:600;">${cam.count || 0} vehicles (24h)</span>
                </div>
            `);
        nodeMarkers.push(marker);
    });
}

// ── Flow Trend Chart ───────────────────────────────────────────────────────

function renderFlowChart(flowData) {
    if (!flowData) return;

    const ctx = document.getElementById('flowChart').getContext('2d');

    if (flowChart) { flowChart.destroy(); }

    const gradient = ctx.createLinearGradient(0, 0, 0, 220);
    gradient.addColorStop(0, 'rgba(99, 102, 241, 0.5)');
    gradient.addColorStop(1, 'rgba(99, 102, 241, 0.0)');

    flowChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: flowData.labels,
            datasets: [{
                label: 'Vehicles',
                data: flowData.data,
                borderColor: '#818cf8',
                backgroundColor: gradient,
                borderWidth: 2.5,
                pointBackgroundColor: '#6366f1',
                pointRadius: 3,
                pointHoverRadius: 6,
                fill: true,
                tension: 0.4,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1e2130',
                    borderColor: '#818cf8',
                    borderWidth: 1,
                    titleColor: '#a5b4fc',
                    bodyColor: '#e2e8f0',
                    padding: 10,
                    callbacks: {
                        label: ctx => ` ${ctx.raw} vehicles`,
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: '#64748b', font: { size: 10 }, maxTicksLimit: 12 },
                    grid: { color: 'rgba(255,255,255,0.04)' },
                },
                y: {
                    ticks: { color: '#64748b', font: { size: 10 } },
                    grid: { color: 'rgba(255,255,255,0.06)' },
                    beginAtZero: true,
                }
            }
        }
    });
}

// ── OD Matrix ─────────────────────────────────────────────────────────────

function renderODMatrix(odData) {
    const container = document.getElementById('odMatrix');
    if (!odData || !odData.lanes) {
        container.innerHTML = '<div class="no-data-msg">No OD data available yet. More plate events needed.</div>';
        return;
    }

    const { matrix, lanes } = odData;
    const allCounts = matrix.flatMap(r => Object.values(r.destinations));
    const maxCount = Math.max(1, ...allCounts);

    let html = `<table class="od-table">
        <thead><tr>
            <th style="text-align:left;">From \\ To</th>
            ${lanes.map(l => `<th>${l}</th>`).join('')}
        </tr></thead>
        <tbody>`;

    matrix.forEach(row => {
        html += `<tr><td class="od-row-label">${row.origin}</td>`;
        lanes.forEach(dest => {
            if (dest === row.origin) {
                html += `<td class="od-self">—</td>`;
            } else {
                const count = row.destinations[dest] || 0;
                const ratio = count / maxCount;
                const cls   = ratio > 0.6 ? 'od-cell-high' : ratio > 0.2 ? 'od-cell-med' : '';
                html += `<td class="${cls}">${count}</td>`;
            }
        });
        html += '</tr>';
    });

    html += `</tbody></table>`;

    if (odData.top_routes && odData.top_routes.length > 0) {
        html += `<div style="margin-top:0.75rem;padding-top:0.75rem;border-top:1px solid rgba(255,255,255,0.06);">
            <div style="font-size:0.7rem;font-weight:600;color:var(--text-muted);margin-bottom:0.5rem;">TOP ROUTES</div>
            ${odData.top_routes.map(r => `
                <div style="display:flex;justify-content:space-between;font-size:0.75rem;padding:0.25rem 0;border-bottom:1px solid rgba(255,255,255,0.04);">
                    <span style="color:var(--text-secondary);">${r.route}</span>
                    <span style="color:#818cf8;font-weight:700;">${r.count}</span>
                </div>`).join('')}
        </div>`;
    }

    container.innerHTML = html;
}

// ── Speed Cards ────────────────────────────────────────────────────────────

function renderSpeedCards(speeds) {
    const grid = document.getElementById('speedGrid');
    if (!speeds || speeds.length === 0) {
        grid.innerHTML = '<div class="no-data-msg" style="grid-column:1/-1;">No cross-camera speed data yet.</div>';
        return;
    }

    grid.innerHTML = speeds.map(s => {
        const cls = s.status ? s.status.toLowerCase() : 'normal';
        return `
            <div class="speed-card">
                <div class="speed-route">
                    <i class="fa-solid fa-arrow-right-long"></i>
                    ${s.from_cam} → ${s.to_cam}
                </div>
                <div class="speed-value ${cls}">${s.avg_speed_kmh} <small style="font-size:0.75rem;font-weight:500;">km/h</small></div>
                <div class="speed-meta">
                    Peak: ${s.max_speed_kmh} km/h &nbsp;|&nbsp; Samples: ${s.sample_count}
                </div>
            </div>`;
    }).join('');
}

// ── Congestion ─────────────────────────────────────────────────────────────

function renderCongestion(congestion) {
    const list = document.getElementById('congestionList');
    if (!congestion || congestion.length === 0) {
        list.innerHTML = '<div class="no-data-msg">No congestion detected currently. Traffic flowing normally.</div>';
        return;
    }

    list.innerHTML = congestion.map(c => `
        <div class="congestion-item">
            <span class="congestion-badge ${c.severity.toLowerCase()}">${c.severity}</span>
            <span class="congestion-name">${c.name}</span>
            <span class="congestion-count">${c.vehicle_count} veh/h</span>
        </div>
    `).join('');
}

// ── Alert Badge ─────────────────────────────────────────────────────────────

function updateAlertBadge() {
    fetch('/api/alerts/summary')
        .then(r => r.json())
        .then(data => {
            const badge = document.getElementById('navAlertBadge');
            const active = data.active || 0;
            badge.textContent = active;
            badge.style.display = active > 0 ? 'inline-flex' : 'none';
        })
        .catch(() => {});
}
