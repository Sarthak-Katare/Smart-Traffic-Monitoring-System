/**
 * Smart Traffic Optimization System - History & Logs JavaScript
 * Phase 10: SQLite Database Analytics & Historical Record Table
 */

document.addEventListener('DOMContentLoaded', () => {
    console.log('[TRAFFIC AI] History Page Initialized');

    const historyTableBody = document.getElementById('historyTableBody');
    const histTotalRecords = document.getElementById('histTotalRecords');
    const histAvgVehicles  = document.getElementById('histAvgVehicles');
    const histCongestedLane= document.getElementById('histCongestedLane');

    loadHistoryLogs();
    setInterval(loadHistoryLogs, 5000); // Auto refresh table every 5 seconds

    async function loadHistoryLogs() {
        try {
            const response = await fetch('/api/history?limit=50');
            if (!response.ok) return;

            const data = await response.json();
            const logs = data.logs || [];
            const summary = data.summary || {};

            // Update Summary Cards
            if (histTotalRecords) histTotalRecords.innerText = summary.total_records || 0;
            if (histAvgVehicles)  histAvgVehicles.innerText  = summary.avg_vehicles || 0;

            if (histCongestedLane && logs.length > 0) {
                // Determine most frequent green lane
                const counts = {};
                logs.forEach(l => {
                    counts[l.active_green_lane] = (counts[l.active_green_lane] || 0) + 1;
                });
                let maxLane = 'NORTH';
                let maxCount = -1;
                Object.keys(counts).forEach(lane => {
                    if (counts[lane] > maxCount) {
                        maxCount = counts[lane];
                        maxLane = lane.toUpperCase();
                    }
                });
                histCongestedLane.innerText = maxLane;
            }

            // Populate Table
            if (!historyTableBody) return;

            if (logs.length === 0) {
                historyTableBody.innerHTML = `
                    <tr>
                        <td colspan="6" class="text-center" style="padding:2rem;color:#94a3b8;">
                            <i class="fa-solid fa-inbox" style="font-size:1.5rem;margin-bottom:0.5rem;display:block;"></i>
                            No historical records in SQLite database yet. Run the AI traffic stream to start logging cycles automatically.
                        </td>
                    </tr>
                `;
                return;
            }

            historyTableBody.innerHTML = logs.map(log => {
                const laneBadgeColor = getLaneColor(log.active_green_lane);
                const densityLevel = getDensityLevel(log.pcu_total_score);

                return `
                    <tr>
                        <td style="font-family:monospace;color:#06b6d4;">${log.timestamp}</td>
                        <td>
                            <span class="density-badge" style="background:${laneBadgeColor.bg};color:${laneBadgeColor.fg};font-weight:700;">
                                ${log.active_green_lane.toUpperCase()} LANE
                            </span>
                        </td>
                        <td style="font-weight:700;color:#f8fafc;">${log.total_vehicles}</td>
                        <td style="font-size:0.85rem;color:#cbd5e1;">
                            <i class="fa-solid fa-car" style="color:#3b82f6;"></i> ${log.cars_count} &nbsp;|&nbsp; 
                            <i class="fa-solid fa-motorcycle" style="color:#10b981;"></i> ${log.bikes_count} &nbsp;|&nbsp; 
                            <i class="fa-solid fa-bus" style="color:#f59e0b;"></i> ${log.buses_count} &nbsp;|&nbsp; 
                            <i class="fa-solid fa-truck" style="color:#ef4444;"></i> ${log.trucks_count}
                        </td>
                        <td>
                            <span class="density-badge ${densityLevel.toLowerCase()}">${densityLevel} (${log.pcu_total_score} PCU)</span>
                        </td>
                        <td style="font-weight:600;color:#34c759;">
                            ${15 + Math.min(45, Math.round(log.pcu_total_score * 2))}s
                        </td>
                    </tr>
                `;
            }).join('');

        } catch (err) {
            console.error('[HISTORY] Load error:', err);
        }
    }

    function getLaneColor(lane) {
        switch (lane) {
            case 'North': return { bg: 'rgba(6,182,212,0.2)', fg: '#06b6d4' };
            case 'South': return { bg: 'rgba(245,158,11,0.2)', fg: '#f59e0b' };
            case 'East':  return { bg: 'rgba(16,185,129,0.2)', fg: '#10b981' };
            case 'West':  return { bg: 'rgba(168,85,247,0.2)', fg: '#c084fc' };
            default:      return { bg: 'rgba(148,163,184,0.2)', fg: '#94a3b8' };
        }
    }

    function getDensityLevel(pcu) {
        if (pcu <= 3.0) return 'LOW';
        if (pcu <= 7.0) return 'MEDIUM';
        if (pcu <= 12.0) return 'HIGH';
        return 'CRITICAL';
    }
});
