/**
 * trajectory.js — Vehicle Trajectory Map & Timeline
 * Leaflet.js map with camera node markers and polyline path rendering
 */

let map = null;
let cameraMarkers = [];
let trajectoryLayer = null;
let waypointMarkers = [];

const DEMO_PLATES = [
    'DL 01 AB 1234', 'MH 12 DE 1433', 'KA 05 MJ 9988',
    'DL09XY7799', 'UP16CD7712'
];

// ── Initialize on page load ────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    loadCameraNodes();
    buildQuickPlates();
    updateAlertBadge();
    setInterval(updateAlertBadge, 10000);

    // Allow Enter key in search input
    document.getElementById('plateInput').addEventListener('keydown', e => {
        if (e.key === 'Enter') searchTrajectory();
    });
    // Auto-uppercase the plate input
    document.getElementById('plateInput').addEventListener('input', e => {
        const cur = e.target.selectionStart;
        e.target.value = e.target.value.toUpperCase();
        e.target.setSelectionRange(cur, cur);
    });
});

// ── Map Initialization ─────────────────────────────────────────────────────

function initMap() {
    map = L.map('trajectoryMap', {
        center: [28.6100, 77.1800],
        zoom: 11,
        zoomControl: true,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 18,
    }).addTo(map);
}

function loadCameraNodes() {
    fetch('/api/trajectory/nodes')
        .then(r => r.json())
        .then(data => {
            if (!data.success) return;
            renderCameraNodes(data.nodes);
        })
        .catch(() => {});
}

function renderCameraNodes(nodes) {
    // Clear old markers
    cameraMarkers.forEach(m => map.removeLayer(m));
    cameraMarkers = [];

    nodes.forEach(node => {
        const intensity = node.intensity || 0;
        const color = intensityColor(intensity);

        const icon = L.divIcon({
            className: '',
            html: `<div style="
                width:44px; height:44px;
                background:${color};
                border:3px solid rgba(255,255,255,0.85);
                border-radius:50%;
                box-shadow:0 0 18px ${color}, 0 2px 8px rgba(0,0,0,0.5);
                display:flex; align-items:center; justify-content:center;
                font-size:0.6rem; font-weight:800; color:#fff;
                font-family:'Inter',sans-serif;
                cursor:pointer;
            ">${node.id.substring(0,1)}</div>`,
            iconSize: [44, 44],
            iconAnchor: [22, 22],
            popupAnchor: [0, -24],
        });

        const marker = L.marker([node.lat, node.lon], { icon })
            .addTo(map)
            .bindPopup(`
                <div style="font-family:'Inter',sans-serif;min-width:180px;">
                    <div style="font-size:0.8rem;font-weight:700;margin-bottom:4px;">${node.name}</div>
                    <div style="font-size:0.72rem;color:#6b7280;">${node.city_zone}</div>
                    <div style="font-size:0.72rem;margin-top:6px;">
                        <span style="background:#4f46e5;color:#fff;padding:2px 8px;border-radius:4px;">
                            ${node.vehicle_count_24h} vehicles (24h)
                        </span>
                    </div>
                    <div style="margin-top:8px;">
                        <a href="#" onclick="event.preventDefault();quickSearchFromNode('${node.id}')"
                           style="font-size:0.72rem;color:#818cf8;text-decoration:none;font-weight:600;">
                           View recent events →
                        </a>
                    </div>
                </div>
            `, { className: 'custom-popup' });

        cameraMarkers.push(marker);
    });
}

function intensityColor(v) {
    if (v < 0.1) return '#6366f1';
    if (v < 0.4) return '#8b5cf6';
    if (v < 0.7) return '#f59e0b';
    return '#ef4444';
}

// ── Trajectory Search ──────────────────────────────────────────────────────

function searchTrajectory() {
    const plate = document.getElementById('plateInput').value.trim();
    if (!plate) return;

    document.getElementById('trajTimeline').innerHTML = `
        <div class="loading-spinner">
            <i class="fa-solid fa-circle-notch spin" style="font-size:1.8rem;color:#818cf8;"></i>
            <p style="margin-top:0.75rem;">Reconstructing trajectory for <b>${plate}</b>…</p>
        </div>`;

    fetch(`/api/trajectory/${encodeURIComponent(plate)}`)
        .then(r => r.json())
        .then(data => {
            if (!data.found || data.waypoints.length === 0) {
                document.getElementById('trajTimeline').innerHTML = `
                    <div class="no-results">
                        <i class="fa-solid fa-circle-xmark"></i>
                        <h3>No Trajectory Found</h3>
                        <p>Plate <b>${plate}</b> has not been detected by any camera node yet.<br>
                        Seed demo data first or wait for live ANPR detection.</p>
                    </div>`;
                clearMapTrajectory();
                return;
            }
            renderTimeline(data);
            renderMapTrajectory(data);
        })
        .catch(() => {
            document.getElementById('trajTimeline').innerHTML = `
                <div class="no-results">
                    <i class="fa-solid fa-triangle-exclamation"></i>
                    <h3>Request Failed</h3>
                    <p>Could not fetch trajectory. Check server connection.</p>
                </div>`;
        });
}

function clearMapTrajectory() {
    waypointMarkers.forEach(m => map.removeLayer(m));
    waypointMarkers = [];
    if (trajectoryLayer) { map.removeLayer(trajectoryLayer); trajectoryLayer = null; }
}

function renderMapTrajectory(data) {
    clearMapTrajectory();

    const latlngs = data.waypoints.map(wp => [wp.lat, wp.lon]);

    // Draw path
    trajectoryLayer = L.polyline(latlngs, {
        color: '#818cf8',
        weight: 4,
        opacity: 0.85,
        dashArray: '8, 6',
    }).addTo(map);

    // Draw waypoint markers
    data.waypoints.forEach((wp, i) => {
        const isFirst = i === 0;
        const isLast  = i === data.waypoints.length - 1;
        const color = isFirst ? '#10b981' : isLast ? '#f59e0b' : '#6366f1';

        const icon = L.divIcon({
            className: '',
            html: `<div style="
                width:32px; height:32px;
                background:${color};
                border:2px solid #fff;
                border-radius:50%;
                box-shadow:0 0 12px ${color};
                display:flex; align-items:center; justify-content:center;
                font-size:0.65rem; font-weight:800; color:#fff;
            ">${wp.seq}</div>`,
            iconSize: [32, 32],
            iconAnchor: [16, 16],
            popupAnchor: [0, -20],
        });

        const m = L.marker([wp.lat, wp.lon], { icon })
            .addTo(map)
            .bindPopup(`
                <div style="font-family:'Inter',sans-serif;min-width:170px;">
                    <div style="font-weight:700;font-size:0.78rem;">#${wp.seq} — ${wp.camera_name}</div>
                    <div style="font-size:0.7rem;color:#6b7280;margin-top:2px;">${wp.city_zone}</div>
                    <div style="font-size:0.7rem;margin-top:5px;">
                        <b>Time:</b> ${wp.timestamp}<br>
                        <b>Confidence:</b> ${wp.confidence}%<br>
                        <b>Class:</b> ${wp.vehicle_class}
                        ${wp.time_gap_min !== null ? `<br><b>Gap:</b> ${wp.time_gap_min} min` : ''}
                        ${wp.distance_km !== null ? `<br><b>Distance:</b> ${wp.distance_km} km` : ''}
                    </div>
                </div>
            `);

        waypointMarkers.push(m);
    });

    // Fit map to trajectory bounds
    map.fitBounds(trajectoryLayer.getBounds().pad(0.25));
}

function renderTimeline(data) {
    const stats = data.stats;
    const wps   = data.waypoints;

    let html = `
        <div class="traj-stats-bar">
            <div class="traj-stat">
                <div class="label">Total Sightings</div>
                <div class="value">${stats.total_sightings}</div>
            </div>
            <div class="traj-stat">
                <div class="label">Cameras Visited</div>
                <div class="value">${stats.unique_cameras}</div>
            </div>
            <div class="traj-stat">
                <div class="label">Duration</div>
                <div class="value">${stats.duration_min} min</div>
            </div>
            <div class="traj-stat">
                <div class="label">Total Distance</div>
                <div class="value">${stats.total_distance_km} km</div>
            </div>
        </div>
        <ul class="timeline-list">`;

    wps.forEach((wp, i) => {
        const isFirst = i === 0;
        const isLast  = i === wps.length - 1;
        const dotClass = isFirst ? 'first' : isLast ? 'last' : '';

        if (i > 0 && wp.time_gap_min !== null) {
            html += `<div class="timeline-gap"><i class="fa-solid fa-arrow-down" style="font-size:0.55rem;"></i> ${wp.time_gap_min} min — ${wp.distance_km || '?'} km</div>`;
        }

        html += `
            <li class="timeline-item">
                <div class="timeline-dot ${dotClass}">${wp.seq}</div>
                <div class="timeline-content">
                    <div class="cam-name">${wp.camera_name}</div>
                    <div class="cam-zone">${wp.city_zone}</div>
                    <div class="cam-time">${wp.timestamp}</div>
                    <div class="cam-meta">
                        <span class="meta-chip"><i class="fa-solid fa-shield"></i> ${wp.confidence}%</span>
                        <span class="meta-chip">${wp.vehicle_class}</span>
                        ${isFirst ? '<span class="meta-chip" style="background:rgba(16,185,129,0.15);color:#34d399;">START</span>' : ''}
                        ${isLast  ? '<span class="meta-chip" style="background:rgba(245,158,11,0.15);color:#fbbf24;">LAST SEEN</span>' : ''}
                    </div>
                </div>
            </li>`;
    });

    html += '</ul>';
    document.getElementById('trajTimeline').innerHTML = html;
}

// ── Quick Helpers ──────────────────────────────────────────────────────────

function buildQuickPlates() {
    const container = document.getElementById('quickPlates');
    DEMO_PLATES.forEach(plate => {
        const chip = document.createElement('span');
        chip.className = 'quick-plate-chip';
        chip.textContent = plate;
        chip.onclick = () => {
            document.getElementById('plateInput').value = plate;
            searchTrajectory();
        };
        container.appendChild(chip);
    });
}

function quickSearchFromNode(camId) {
    // Show recent events for this camera
    fetch(`/api/trajectory/recent?limit=10`)
        .then(r => r.json())
        .then(data => {
            if (!data.events || data.events.length === 0) {
                showToast('No recent events for this camera yet.', 'info');
                return;
            }
            // Filter by camera
            const camEvents = data.events.filter(e => e.camera_id === camId);
            if (camEvents.length > 0) {
                const plate = camEvents[0].plate;
                document.getElementById('plateInput').value = plate;
                searchTrajectory();
            } else {
                showToast('No recent events for this camera.', 'info');
            }
        });
}

function seedDemoData() {
    const btn = document.getElementById('btnSeedDemo');
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-circle-notch spin"></i> Seeding…';

    fetch('/api/trajectory/seed_demo', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            btn.innerHTML = `<i class="fa-solid fa-check"></i> ${data.events_seeded} Events Seeded!`;
            loadCameraNodes();
            showToast(`${data.events_seeded} demo trajectory events seeded. Search any plate above.`, 'success');
            setTimeout(() => {
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-database"></i> Seed Demo Trajectory Data';
            }, 3000);
        })
        .catch(() => {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-database"></i> Seed Demo Trajectory Data';
        });
}

function updateAlertBadge() {
    fetch('/api/alerts/summary')
        .then(r => r.json())
        .then(data => {
            const badge = document.getElementById('navAlertBadge');
            const active = data.active || 0;
            if (active > 0) {
                badge.textContent = active;
                badge.style.display = 'inline-flex';
            } else {
                badge.style.display = 'none';
            }
        })
        .catch(() => {});
}

function showToast(msg, type = 'info') {
    const container = document.getElementById('toastContainer') || document.body;
    const toast = document.createElement('div');
    const colors = { success: '#10b981', info: '#818cf8', error: '#ef4444' };
    toast.style.cssText = `
        position:fixed; bottom:24px; right:24px; z-index:9999;
        background:#1e2130; border:1px solid ${colors[type]};
        border-left:4px solid ${colors[type]};
        border-radius:10px; padding:0.85rem 1.25rem;
        font-family:'Inter',sans-serif; font-size:0.82rem; color:#e2e8f0;
        box-shadow:0 4px 24px rgba(0,0,0,0.5);
        animation:fadeInUp 0.3s ease;
        max-width:320px; line-height:1.4;
    `;
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}
