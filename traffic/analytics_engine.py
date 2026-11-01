"""
analytics_engine.py — City Traffic Flow & Macro Analytics Engine

Computes:
  - Heatmap intensity data per camera node
  - Origin-destination (OD) movement matrix
  - Hourly traffic flow trends
  - Speed estimates between camera pairs
  - Congestion bottleneck identification
"""

from traffic.trajectory_engine import CAMERA_NODES


class AnalyticsEngine:
    """
    Aggregates plate_events from database into macro city-wide traffic analytics.
    """

    # Congestion threshold: vehicles per hour at a single camera node
    CONGESTION_THRESHOLD = 30

    def __init__(self, db_manager):
        self.db = db_manager

    def get_heatmap_data(self, hours=24):
        """
        Returns heatmap points for Leaflet.heat overlay.
        Format: [ {lat, lon, intensity, camera_id, count} ]
        Merges DB event counts with static node coordinates.
        """
        db_counts = {row['camera_id']: row for row in self.db.get_camera_event_counts(hours=hours)}

        points = []
        max_count = max((row['count'] for row in db_counts.values()), default=1)
        max_count = max(max_count, 1)

        for cam_id, node in CAMERA_NODES.items():
            db_row = db_counts.get(cam_id, {})
            count = db_row.get('count', 0)
            intensity = round(count / max_count, 3) if max_count > 0 else 0.0
            points.append({
                'camera_id': cam_id,
                'lat': node['lat'],
                'lon': node['lon'],
                'count': count,
                'intensity': max(0.05, intensity),  # minimum glow even at 0
                'name': node['name'],
                'city_zone': node['city_zone'],
            })
        return points

    def get_flow_trends(self, hours=24):
        """
        Returns hourly vehicle count trend for Chart.js line chart.
        Fills in missing hours with 0.
        Format: { labels: ['00','01',...,'23'], data: [12, 8, ...] }
        """
        db_rows = self.db.get_hourly_flow(hours=hours)
        hourly_map = {row['hour']: row['count'] for row in db_rows}

        labels = [f"{h:02d}:00" for h in range(24)]
        data = [hourly_map.get(f"{h:02d}", 0) for h in range(24)]

        return {
            'labels': labels,
            'data': data,
            'total_vehicles': sum(data),
            'peak_hour': labels[data.index(max(data))] if any(data) else 'N/A',
            'peak_count': max(data) if any(data) else 0,
        }

    def get_od_matrix(self, hours=24):
        """
        Returns origin-destination matrix as structured table data.
        Format: { 'North_TO_East': count, ... }
        Also returns table-friendly format.
        """
        raw = self.db.get_od_matrix(hours=hours)
        lanes = list(CAMERA_NODES.keys())

        # Build full NxN matrix
        matrix = []
        for origin in lanes:
            row = {'origin': origin, 'destinations': {}}
            for dest in lanes:
                if origin != dest:
                    key = f"{origin}_TO_{dest}"
                    row['destinations'][dest] = raw.get(key, 0)
            matrix.append(row)

        # Top routes
        top_routes = sorted(
            [{'route': k.replace('_TO_', ' → '), 'count': v} for k, v in raw.items()],
            key=lambda x: x['count'],
            reverse=True
        )[:5]

        return {
            'matrix': matrix,
            'raw': raw,
            'top_routes': top_routes,
            'lanes': lanes,
        }

    def get_speed_estimates(self):
        """Returns inter-camera speed estimates enriched with node names."""
        raw = self.db.get_speed_estimates()
        enriched = []
        for item in raw:
            from_node = CAMERA_NODES.get(item['from_cam'], {})
            to_node = CAMERA_NODES.get(item['to_cam'], {})
            enriched.append({
                **item,
                'from_name': from_node.get('name', item['from_cam']),
                'to_name': to_node.get('name', item['to_cam']),
                'status': _speed_status(item['avg_speed_kmh']),
            })
        return enriched

    def get_congestion_nodes(self, hours=1):
        """
        Returns list of camera nodes with vehicle count above congestion threshold.
        """
        counts = {row['camera_id']: row['count']
                  for row in self.db.get_camera_event_counts(hours=hours)}
        congested = []
        for cam_id, node in CAMERA_NODES.items():
            count = counts.get(cam_id, 0)
            if count >= self.CONGESTION_THRESHOLD:
                congested.append({
                    'camera_id': cam_id,
                    'name': node['name'],
                    'city_zone': node['city_zone'],
                    'vehicle_count': count,
                    'severity': 'HIGH' if count >= self.CONGESTION_THRESHOLD * 2 else 'MODERATE',
                })
        return congested

    def get_full_dashboard(self):
        """Returns all analytics data in one call for the analytics page."""
        return {
            'heatmap': self.get_heatmap_data(),
            'flow_trends': self.get_flow_trends(),
            'od_matrix': self.get_od_matrix(),
            'speed_estimates': self.get_speed_estimates(),
            'congestion': self.get_congestion_nodes(),
            'camera_nodes': [
                {'id': k, 'name': v['name'], 'lat': v['lat'],
                 'lon': v['lon'], 'zone': v['city_zone']}
                for k, v in CAMERA_NODES.items()
            ],
        }


def _speed_status(speed_kmh):
    if speed_kmh < 20:
        return 'SLOW'
    if speed_kmh < 50:
        return 'MODERATE'
    if speed_kmh < 80:
        return 'NORMAL'
    return 'FAST'
