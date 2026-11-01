/**
 * alerts.js — Alert Management & Blacklist System
 * Real-time alert feed, blacklist CRUD, alert resolve
 */

let currentFilter = 'active';
let lastAlertIds  = new Set();

document.addEventListener('DOMContentLoaded', () => {
    loadAlerts();
    loadBlacklist();
    updateAlertBadge();

    // Poll alerts every 4 seconds
    setInterval(() => {
        loadAlerts();
        updateAlertBadge();
    }, 4000);
    // Poll blacklist every 15 seconds
    setInterval(loadBlacklist, 15000);

    // Enter key in add-blacklist form
    document.getElementById('blPlateInput').addEventListener('keydown', e => {
        if (e.key === 'Enter') addToBlacklist();
    });
    // Auto uppercase plate input
    document.getElementById('blPlateInput').addEventListener('input', e => {
        const cur = e.target.selectionStart;
        e.target.value = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
        e.target.setSelectionRange(cur, cur);
    });
});

// ── Load & Render Alerts ───────────────────────────────────────────────────

function loadAlerts() {
    fetch('/api/alerts')
        .then(r => r.json())
        .then(data => {
            renderSummary(data.summary);
            const alerts = currentFilter === 'active' ? data.alerts : data.all_alerts;
            renderAlertFeed(alerts || []);
            checkForNewAlerts(data.alerts || []);
        })
        .catch(() => {});
}

function setFilter(filter, btn) {
    currentFilter = filter;
    document.querySelectorAll('.alert-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    loadAlerts();
}

function renderSummary(summary) {
    if (!summary) return;
    document.getElementById('summCritical').textContent = summary.critical || 0;
    document.getElementById('summWarning').textContent  = summary.warnings || 0;
    document.getElementById('summActive').textContent   = summary.active   || 0;
    document.getElementById('summTotal').textContent    = summary.total    || 0;

    // Update nav badge
    const badge = document.getElementById('navAlertBadge');
    badge.textContent = summary.active || 0;
    badge.style.display = (summary.active > 0) ? 'inline-flex' : 'none';
}

function renderAlertFeed(alerts) {
    const feed = document.getElementById('alertFeed');
    if (!alerts || alerts.length === 0) {
        feed.innerHTML = `
            <div class="no-alerts-msg">
                <i class="fa-solid fa-shield-check"></i>
                <br>No ${currentFilter === 'active' ? 'active' : ''} alerts.<br>
                <small>System monitoring all camera nodes…</small>
            </div>`;
        return;
    }

    feed.innerHTML = alerts.map(a => {
        const sev        = (a.severity || 'WARNING').toLowerCase();
        const isResolved = a.resolved === 1 || a.resolved === true;
        const typeIcon   = a.alert_type === 'BLACKLIST_HIT'
            ? '<i class="fa-solid fa-ban"></i>'
            : '<i class="fa-solid fa-triangle-exclamation"></i>';

        return `
        <div class="alert-item ${sev} ${isResolved ? 'resolved' : ''}" id="alert-${a.id}">
            <div class="alert-item-top">
                <div style="display:flex;align-items:center;gap:0.5rem;">
                    <span class="alert-severity ${sev}">${typeIcon} ${a.severity}</span>
                    <span class="alert-plate">${a.plate}</span>
                </div>
                <span style="font-size:0.68rem;color:var(--text-muted);">${a.camera_id} Camera</span>
            </div>
            <div class="alert-message">${a.message}</div>
            <div class="alert-meta">
                <span class="alert-ts">${a.timestamp}</span>
                ${isResolved
                    ? `<span class="resolved-badge"><i class="fa-solid fa-check-circle"></i> Resolved</span>`
                    : `<button class="btn-resolve" onclick="resolveAlert(${a.id})">
                           <i class="fa-solid fa-check"></i> Resolve
                       </button>`
                }
            </div>
        </div>`;
    }).join('');
}

function checkForNewAlerts(activeAlerts) {
    if (!activeAlerts) return;
    const currentIds = new Set(activeAlerts.map(a => a.id));
    // Show toast for any brand-new alert
    activeAlerts.forEach(a => {
        if (!lastAlertIds.has(a.id)) {
            const sev = (a.severity || 'warning').toLowerCase();
            showSystemToast(a);
        }
    });
    lastAlertIds = currentIds;
}

function resolveAlert(alertId) {
    fetch(`/api/alerts/resolve/${alertId}`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                const el = document.getElementById(`alert-${alertId}`);
                if (el) el.classList.add('resolved');
                loadAlerts();
            }
        });
}

// ── Blacklist ──────────────────────────────────────────────────────────────

function loadBlacklist() {
    fetch('/api/blacklist')
        .then(r => r.json())
        .then(data => {
            renderBlacklist(data.blacklist || []);
        })
        .catch(() => {});
}

function renderBlacklist(list) {
    const tbody = document.getElementById('blacklistBody');
    const countEl = document.getElementById('blCount');
    countEl.textContent = `(${list.length})`;

    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:1.5rem;color:var(--text-muted);font-size:0.78rem;">Blacklist is empty.</td></tr>`;
        return;
    }

    tbody.innerHTML = list.map(entry => {
        const shortReason = entry.reason.length > 40
            ? entry.reason.substring(0, 40) + '…'
            : entry.reason;
        return `
        <tr>
            <td><span class="bl-plate">${entry.plate}</span></td>
            <td><span class="bl-reason" title="${entry.reason}">${shortReason}</span></td>
            <td style="font-size:0.7rem;color:var(--text-muted);">${entry.flagged_by || 'System'}</td>
            <td>
                <button class="btn-remove-bl" onclick="removeFromBlacklist('${entry.plate}')">
                    <i class="fa-solid fa-trash-can"></i> Remove
                </button>
            </td>
        </tr>`;
    }).join('');
}

function addToBlacklist() {
    const plate  = document.getElementById('blPlateInput').value.trim();
    const reason = document.getElementById('blReasonInput').value.trim() || 'Flagged by Operator';
    const fb     = document.getElementById('blFeedback');

    if (!plate) {
        showFeedback(fb, 'Please enter a plate number.', false);
        return;
    }

    fetch('/api/blacklist/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plate, reason }),
    })
        .then(r => r.json())
        .then(data => {
            showFeedback(fb, data.message, data.success);
            if (data.success) {
                document.getElementById('blPlateInput').value = '';
                document.getElementById('blReasonInput').value = '';
                loadBlacklist();
            }
        })
        .catch(() => showFeedback(fb, 'Request failed. Check server.', false));
}

function removeFromBlacklist(plate) {
    if (!confirm(`Remove "${plate}" from the blacklist?`)) return;
    fetch(`/api/blacklist/remove/${encodeURIComponent(plate)}`, { method: 'DELETE' })
        .then(r => r.json())
        .then(data => {
            if (data.success) loadBlacklist();
        });
}

function showFeedback(el, msg, success) {
    el.style.display = 'block';
    el.style.color   = success ? '#34d399' : '#f87171';
    el.innerHTML     = `<i class="fa-solid fa-${success ? 'check' : 'xmark'}-circle"></i> ${msg}`;
    setTimeout(() => { el.style.display = 'none'; }, 4000);
}

// ── Alert Badge ────────────────────────────────────────────────────────────

function updateAlertBadge() {
    fetch('/api/alerts/summary')
        .then(r => r.json())
        .then(data => {
            const badge = document.getElementById('navAlertBadge');
            badge.textContent = data.active || 0;
            badge.style.display = data.active > 0 ? 'inline-flex' : 'none';
        })
        .catch(() => {});
}

// ── System Toast for Critical Alerts ──────────────────────────────────────

function showSystemToast(alert) {
    const isCritical = alert.severity === 'CRITICAL';
    const toast = document.createElement('div');
    toast.style.cssText = `
        position:fixed; bottom:24px; right:24px; z-index:9999;
        background:#1e2130;
        border:1px solid ${isCritical ? '#ef4444' : '#f59e0b'};
        border-left:4px solid ${isCritical ? '#ef4444' : '#f59e0b'};
        border-radius:12px; padding:1rem 1.25rem;
        font-family:'Inter',sans-serif; color:#e2e8f0;
        box-shadow:0 4px 24px rgba(0,0,0,0.6);
        max-width:360px; min-width:280px;
        animation:fadeInUp 0.3s ease;
    `;
    toast.innerHTML = `
        <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.4rem;">
            <i class="fa-solid fa-${isCritical ? 'siren-on' : 'triangle-exclamation'}"
               style="color:${isCritical ? '#ef4444' : '#f59e0b'};font-size:1rem;"></i>
            <span style="font-weight:700;font-size:0.85rem;">
                ${isCritical ? 'CRITICAL ALERT' : 'WARNING'}
            </span>
            <span style="font-family:'JetBrains Mono',monospace;font-size:0.8rem;font-weight:700;color:#e2e8f0;margin-left:auto;">
                ${alert.plate}
            </span>
        </div>
        <div style="font-size:0.75rem;color:#94a3b8;line-height:1.4;">${alert.message}</div>
    `;
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.5s'; setTimeout(() => toast.remove(), 500); }, 6000);
}
