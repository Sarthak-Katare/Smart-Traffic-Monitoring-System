"""
trajectory_engine.py — Vehicle Spatial-Temporal Trajectory Tracking Engine

Manages city-wide camera node registry and reconstructs vehicle travel paths
across distributed ANPR camera nodes using plate_events from the database.
"""

import datetime

# ─── City Camera Node Registry ───────────────────────────────────────────────
# GPS coordinates for 4 camera nodes placed at real Delhi intersections
CAMERA_NODES = {
    'North': {
        'name': 'North Gate — Connaught Place Intersection',
        'lat': 28.6315,
        'lon': 77.2167,
        'address': 'Connaught Place, New Delhi - 110001',
        'city_zone': 'Central Delhi',
    },
    'East': {
        'name': 'East Gate — ITO Signal Junction',
        'lat': 28.6280,
        'lon': 77.2410,
        'address': 'ITO Intersection, IP Estate, New Delhi - 110002',
        'city_zone': 'East Delhi',
    },
    'South': {
        'name': 'South Gate — Lajpat Nagar Flyover',
        'lat': 28.5677,
        'lon': 77.2434,
        'address': 'Ring Road, Lajpat Nagar, New Delhi - 110024',
        'city_zone': 'South Delhi',
    },
    'West': {
        'name': 'West Gate — Janakpuri District Centre',
        'lat': 28.6297,
        'lon': 77.0823,
        'address': 'District Centre, Janakpuri, New Delhi - 110058',
        'city_zone': 'West Delhi',
    },
}


class TrajectoryEngine:
    """
    Handles vehicle trajectory logging and reconstruction across city camera nodes.
    Wraps DatabaseManager to provide high-level trajectory API.
    """

    def __init__(self, db_manager):
        self.db = db_manager

    def get_camera_nodes(self):
        """Returns camera node registry with GPS + event counts for map rendering."""
        # Get per-camera event counts from last 24 hours
        event_counts = {row['camera_id']: row['count']
                        for row in self.db.get_camera_event_counts(hours=24)}

        nodes = []
        for cam_id, info in CAMERA_NODES.items():
            count = event_counts.get(cam_id, 0)
            # Intensity 0.0–1.0 scaled at 100 vehicles = max intensity
            intensity = min(1.0, count / 100.0)
            nodes.append({
                'id': cam_id,
                'name': info['name'],
                'lat': info['lat'],
                'lon': info['lon'],
                'address': info['address'],
                'city_zone': info['city_zone'],
                'vehicle_count_24h': count,
                'intensity': round(intensity, 3),
            })
        return nodes

    def log_sighting(self, plate, camera_id, confidence=0.0, vehicle_class='unknown'):
        """
        Logs an ANPR plate sighting at a camera node.
        Looks up GPS from the camera registry.
        Returns True on success.
        """
        node = CAMERA_NODES.get(camera_id)
        if not node:
            return False
        return self.db.log_plate_event(
            plate=plate,
            camera_id=camera_id,
            lat=node['lat'],
            lon=node['lon'],
            confidence=confidence,
            vehicle_class=vehicle_class,
        )

    def get_trajectory(self, plate):
        """
        Reconstructs the full travel trajectory of a vehicle plate.
        Returns trajectory dict with waypoints, stats, and timeline.
        """
        events = self.db.get_plate_trajectory(plate)
        if not events:
            return {'found': False, 'plate': plate, 'waypoints': [], 'stats': {}}

        waypoints = []
        for i, ev in enumerate(events):
            node_info = CAMERA_NODES.get(ev['camera_id'], {})
            wp = {
                'seq': i + 1,
                'camera_id': ev['camera_id'],
                'camera_name': node_info.get('name', ev['camera_id']),
                'lat': ev['lat'],
                'lon': ev['lon'],
                'timestamp': ev['timestamp'],
                'confidence': ev['confidence'],
                'vehicle_class': ev['vehicle_class'],
                'city_zone': node_info.get('city_zone', ''),
                'time_gap_min': None,
                'distance_km': None,
            }
            if i > 0:
                prev = events[i - 1]
                try:
                    t1 = datetime.datetime.strptime(prev['timestamp'], '%Y-%m-%d %H:%M:%S')
                    t2 = datetime.datetime.strptime(ev['timestamp'], '%Y-%m-%d %H:%M:%S')
                    gap_min = round((t2 - t1).total_seconds() / 60, 1)
                    wp['time_gap_min'] = gap_min
                except Exception:
                    pass
                wp['distance_km'] = round(_haversine(
                    prev['lat'], prev['lon'], ev['lat'], ev['lon']), 2)
            waypoints.append(wp)

        # Stats
        first_ts = events[0]['timestamp']
        last_ts = events[-1]['timestamp']
        cameras_visited = list(dict.fromkeys(e['camera_id'] for e in events))
        total_cameras = len(cameras_visited)

        try:
            t_start = datetime.datetime.strptime(first_ts, '%Y-%m-%d %H:%M:%S')
            t_end = datetime.datetime.strptime(last_ts, '%Y-%m-%d %H:%M:%S')
            duration_min = round((t_end - t_start).total_seconds() / 60, 1)
        except Exception:
            duration_min = 0.0

        total_dist = sum(wp['distance_km'] or 0 for wp in waypoints)

        return {
            'found': True,
            'plate': plate,
            'waypoints': waypoints,
            'stats': {
                'total_sightings': len(events),
                'cameras_visited': cameras_visited,
                'unique_cameras': total_cameras,
                'first_seen': first_ts,
                'last_seen': last_ts,
                'duration_min': duration_min,
                'total_distance_km': round(total_dist, 2),
                'avg_confidence': round(sum(e['confidence'] for e in events) / len(events), 1),
            }
        }

    def get_recent_events(self, limit=50):
        """Returns recent plate sighting events feed for the live events panel."""
        events = self.db.get_recent_plate_events(limit=limit)
        enriched = []
        for ev in events:
            node = CAMERA_NODES.get(ev['camera_id'], {})
            enriched.append({
                **ev,
                'camera_name': node.get('name', ev['camera_id']),
                'city_zone': node.get('city_zone', ''),
            })
        return enriched


def _haversine(lat1, lon1, lat2, lon2):
    """Calculates the Haversine distance between two GPS coordinates (km)."""
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
