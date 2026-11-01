"""
db_manager.py — Extended Traffic Intelligence Database

Tables:
  - traffic_logs        : 10-second intersection snapshots
  - plate_events        : Every ANPR plate sighting with GPS + timestamp
  - blacklist           : Flagged/suspicious plates
  - alerts              : Fired alert records (blacklist hits, anomalies)
"""

import os
import sqlite3
import datetime
import contextlib
import math

DB_PATH = os.path.join(os.path.dirname(__file__), 'traffic.db')


class DatabaseManager:
    """
    SQLite Database Manager for Traffic Intelligence Platform.
    Thread-safe — creates and closes connection per call.
    """

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextlib.contextmanager
    def _get_connection(self):
        """Creates a thread-safe connection to SQLite and closes it when done."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initializes all database tables if they do not exist."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Original traffic snapshot table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS traffic_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    total_vehicles INTEGER DEFAULT 0,
                    cars_count INTEGER DEFAULT 0,
                    bikes_count INTEGER DEFAULT 0,
                    buses_count INTEGER DEFAULT 0,
                    trucks_count INTEGER DEFAULT 0,
                    north_count INTEGER DEFAULT 0,
                    south_count INTEGER DEFAULT 0,
                    east_count INTEGER DEFAULT 0,
                    west_count INTEGER DEFAULT 0,
                    active_green_lane TEXT DEFAULT 'North',
                    pcu_total_score REAL DEFAULT 0.0
                )
            ''')

            # NEW: ANPR plate sighting events (core of trajectory system)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS plate_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lon REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    confidence REAL DEFAULT 0.0,
                    vehicle_class TEXT DEFAULT 'unknown',
                    direction TEXT DEFAULT '',
                    speed_kmh REAL DEFAULT 0.0
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_plate ON plate_events(plate)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_pe_ts ON plate_events(timestamp)')

            # NEW: Blacklisted plates
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS blacklist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate TEXT UNIQUE NOT NULL,
                    reason TEXT DEFAULT 'Flagged',
                    flagged_at TEXT NOT NULL,
                    flagged_by TEXT DEFAULT 'System',
                    is_active INTEGER DEFAULT 1
                )
            ''')

            # NEW: Fired alert records
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    severity TEXT DEFAULT 'WARNING',
                    message TEXT DEFAULT '',
                    timestamp TEXT NOT NULL,
                    resolved INTEGER DEFAULT 0,
                    resolved_at TEXT DEFAULT NULL
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_plate ON alerts(plate)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_res ON alerts(resolved)')

            conn.commit()
            print("[DATABASE] SQLite Traffic Analytics Database initialized.")

    # ==========================================================================
    # Traffic Snapshot Logging (Original)
    # ==========================================================================

    def log_snapshot(self, stats_data):
        """Inserts a single traffic snapshot record into SQLite database."""
        try:
            b = stats_data.get('breakdown', {})
            lanes = stats_data.get('lanes', {})

            north_cnt = lanes.get('North', {}).get('count', 0)
            south_cnt = lanes.get('South', {}).get('count', 0)
            east_cnt  = lanes.get('East', {}).get('count', 0)
            west_cnt  = lanes.get('West', {}).get('count', 0)

            pcu_total = sum(lanes.get(l, {}).get('pcu_score', 0.0) for l in ('North', 'South', 'East', 'West'))
            now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO traffic_logs (
                        timestamp, total_vehicles, cars_count, bikes_count, buses_count, trucks_count,
                        north_count, south_count, east_count, west_count, active_green_lane, pcu_total_score
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    now_str,
                    stats_data.get('total_vehicles', 0),
                    b.get('cars', 0),
                    b.get('motorcycles', 0),
                    b.get('buses', 0),
                    b.get('trucks', 0),
                    north_cnt, south_cnt, east_cnt, west_cnt,
                    stats_data.get('active_green_lane', 'North'),
                    pcu_total
                ))
                conn.commit()
                return True
        except Exception as e:
            print(f"[DATABASE] Log insertion error: {e}")
            return False

    def get_recent_logs(self, limit=50):
        """Fetches the most recent `limit` traffic log entries."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM traffic_logs ORDER BY id DESC LIMIT ?', (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[DATABASE] Fetch error: {e}")
            return []

    def get_summary_analytics(self):
        """Returns high-level aggregate summary statistics."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT
                        COUNT(*) as total_records,
                        COALESCE(MAX(total_vehicles), 0) as max_concurrent_vehicles,
                        COALESCE(AVG(total_vehicles), 0.0) as avg_vehicles,
                        COALESCE(SUM(cars_count), 0) as sum_cars,
                        COALESCE(SUM(bikes_count), 0) as sum_bikes,
                        COALESCE(SUM(buses_count), 0) as sum_buses,
                        COALESCE(SUM(trucks_count), 0) as sum_trucks
                    FROM traffic_logs
                ''')
                row = cursor.fetchone()
                res = dict(row)
                res['avg_vehicles'] = round(res['avg_vehicles'], 1)
                return res
        except Exception as e:
            print(f"[DATABASE] Analytics query error: {e}")
            return {}

    def clear_all_logs(self):
        """Clears all entries from traffic_logs table."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM traffic_logs')
                conn.commit()
                return True
        except Exception as e:
            print(f"[DATABASE] Clear logs error: {e}")
            return False

    # ==========================================================================
    # Plate Events — ANPR Sighting Log (Trajectory System)
    # ==========================================================================

    def log_plate_event(self, plate, camera_id, lat, lon, confidence=0.0,
                        vehicle_class='unknown', direction='', speed_kmh=0.0):
        """Logs a single ANPR plate sighting with GPS coordinates and metadata."""
        try:
            now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO plate_events
                        (plate, camera_id, lat, lon, timestamp, confidence, vehicle_class, direction, speed_kmh)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (plate, camera_id, lat, lon, now_str, confidence, vehicle_class, direction, speed_kmh))
                conn.commit()
                return True
        except Exception as e:
            print(f"[DATABASE] Plate event log error: {e}")
            return False

    def get_plate_trajectory(self, plate):
        """Returns all sighting events for a plate, sorted chronologically."""
        try:
            clean = plate.upper().replace(' ', '').replace('-', '')
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM plate_events
                    WHERE REPLACE(REPLACE(plate, ' ', ''), '-', '') = ?
                    ORDER BY timestamp ASC
                ''', (clean,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[DATABASE] Trajectory query error: {e}")
            return []

    def get_recent_plate_events(self, limit=50):
        """Returns the most recent plate sighting events across all cameras."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM plate_events ORDER BY id DESC LIMIT ?', (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[DATABASE] Recent events query error: {e}")
            return []

    def get_camera_event_counts(self, hours=24):
        """Returns per-camera vehicle counts over the last N hours (for heatmap)."""
        try:
            since = (datetime.datetime.now() - datetime.timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT camera_id, COUNT(*) as count, AVG(lat) as lat, AVG(lon) as lon
                    FROM plate_events
                    WHERE timestamp >= ?
                    GROUP BY camera_id
                ''', (since,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[DATABASE] Camera event count error: {e}")
            return []

    def get_hourly_flow(self, hours=24):
        """Returns vehicle counts grouped by hour for flow trend chart."""
        try:
            since = (datetime.datetime.now() - datetime.timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT strftime('%H', timestamp) as hour, COUNT(*) as count
                    FROM plate_events
                    WHERE timestamp >= ?
                    GROUP BY hour ORDER BY hour
                ''', (since,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[DATABASE] Hourly flow query error: {e}")
            return []

    def get_od_matrix(self, hours=24):
        """Computes origin-destination counts from plate trajectory transitions."""
        try:
            since = (datetime.datetime.now() - datetime.timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT plate, camera_id, timestamp FROM plate_events
                    WHERE timestamp >= ? ORDER BY plate, timestamp
                ''', (since,))
                rows = cursor.fetchall()

            od_counts = {}
            plate_last_cam = {}
            for row in rows:
                plate = row['plate']
                cam = row['camera_id']
                if plate in plate_last_cam and plate_last_cam[plate] != cam:
                    od_key = f"{plate_last_cam[plate]}_TO_{cam}"
                    od_counts[od_key] = od_counts.get(od_key, 0) + 1
                plate_last_cam[plate] = cam
            return od_counts
        except Exception as e:
            print(f"[DATABASE] OD matrix error: {e}")
            return {}

    def get_speed_estimates(self):
        """Estimates speeds between camera pairs using time + GPS distance for same plate."""
        def haversine(lat1, lon1, lat2, lon2):
            R = 6371.0
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT plate, camera_id, lat, lon, timestamp FROM plate_events ORDER BY plate, timestamp')
                rows = [dict(r) for r in cursor.fetchall()]

            speed_data = {}
            plate_prev = {}
            for row in rows:
                plate = row['plate']
                if plate in plate_prev:
                    prev = plate_prev[plate]
                    if prev['camera_id'] != row['camera_id']:
                        try:
                            t1 = datetime.datetime.strptime(prev['timestamp'], '%Y-%m-%d %H:%M:%S')
                            t2 = datetime.datetime.strptime(row['timestamp'], '%Y-%m-%d %H:%M:%S')
                            dt_hours = (t2 - t1).total_seconds() / 3600
                            if 0.0005 < dt_hours < 2.0:
                                dist_km = haversine(prev['lat'], prev['lon'], row['lat'], row['lon'])
                                speed = dist_km / dt_hours
                                if 1 <= speed <= 150:
                                    key = f"{prev['camera_id']}_TO_{row['camera_id']}"
                                    if key not in speed_data:
                                        speed_data[key] = {'speeds': [], 'from': prev['camera_id'], 'to': row['camera_id']}
                                    speed_data[key]['speeds'].append(speed)
                        except Exception:
                            pass
                plate_prev[plate] = row

            result = []
            for key, data in speed_data.items():
                speeds = data['speeds']
                if speeds:
                    result.append({
                        'from_cam': data['from'],
                        'to_cam': data['to'],
                        'avg_speed_kmh': round(sum(speeds) / len(speeds), 1),
                        'max_speed_kmh': round(max(speeds), 1),
                        'sample_count': len(speeds)
                    })
            return result
        except Exception as e:
            print(f"[DATABASE] Speed estimate error: {e}")
            return []

    # ==========================================================================
    # Blacklist Management
    # ==========================================================================

    def add_to_blacklist(self, plate, reason='Flagged', flagged_by='User'):
        """Adds a plate to the blacklist. Returns (success, message)."""
        try:
            clean = plate.upper().replace(' ', '').replace('-', '')
            now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO blacklist (plate, reason, flagged_at, flagged_by, is_active)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(plate) DO UPDATE SET is_active=1, reason=excluded.reason,
                    flagged_at=excluded.flagged_at, flagged_by=excluded.flagged_by
                ''', (clean, reason, now_str, flagged_by))
                conn.commit()
            print(f"[ALERT ENGINE] Plate {clean} added to blacklist: {reason}")
            return True, f"Plate {clean} added to blacklist."
        except Exception as e:
            return False, str(e)

    def remove_from_blacklist(self, plate):
        """Soft-removes a plate from the blacklist."""
        try:
            clean = plate.upper().replace(' ', '').replace('-', '')
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE blacklist SET is_active=0 WHERE plate=?', (clean,))
                conn.commit()
            return True, f"Plate {clean} removed from blacklist."
        except Exception as e:
            return False, str(e)

    def is_blacklisted(self, plate):
        """Returns True if plate is on the active blacklist."""
        try:
            clean = plate.upper().replace(' ', '').replace('-', '')
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM blacklist WHERE plate=? AND is_active=1', (clean,))
                return cursor.fetchone() is not None
        except Exception:
            return False

    def get_blacklist(self):
        """Returns all active blacklisted plates."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM blacklist WHERE is_active=1 ORDER BY flagged_at DESC')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[DATABASE] Blacklist query error: {e}")
            return []

    def seed_blacklist_if_empty(self):
        """Seeds demo blacklist plates if blacklist is empty."""
        if self.get_blacklist():
            return  # Already seeded
        seed_plates = [
            ('DL09XY7799', 'Wanted — Armed Robbery Suspect Vehicle (FIR #DL-2024-4421)', 'Delhi Police'),
            ('MH04TF9001', 'Stolen Vehicle — Reported Missing 2024-02-14 (NCR-STOLEN-2024)', 'Maharashtra Police'),
            ('UP16CD7712', 'Pending Challans Exceeding Rs.50,000 — Court Notice Issued', 'Traffic Enforcement'),
        ]
        for plate, reason, by in seed_plates:
            self.add_to_blacklist(plate, reason, by)
        print("[ALERT ENGINE] Blacklist seeded with 3 demo plates.")

    # ==========================================================================
    # Alerts
    # ==========================================================================

    def create_alert(self, plate, alert_type, camera_id, severity='WARNING', message=''):
        """Creates a new alert record. Returns the new alert id."""
        try:
            now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO alerts (plate, alert_type, camera_id, severity, message, timestamp, resolved)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                ''', (plate, alert_type, camera_id, severity, message, now_str))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            print(f"[DATABASE] Alert creation error: {e}")
            return None

    def get_active_alerts(self, limit=30):
        """Returns recent unresolved alerts."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM alerts WHERE resolved=0 ORDER BY id DESC LIMIT ?', (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[DATABASE] Active alerts query error: {e}")
            return []

    def get_all_alerts(self, limit=100):
        """Returns all alerts (resolved and unresolved)."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM alerts ORDER BY id DESC LIMIT ?', (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            return []

    def resolve_alert(self, alert_id):
        """Marks an alert as resolved."""
        try:
            now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE alerts SET resolved=1, resolved_at=? WHERE id=?', (now_str, alert_id))
                conn.commit()
            return True
        except Exception as e:
            print(f"[DATABASE] Resolve alert error: {e}")
            return False

    def get_alert_summary(self):
        """Returns alert counts by type and severity."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN resolved=0 THEN 1 ELSE 0 END) as active,
                        SUM(CASE WHEN severity='CRITICAL' AND resolved=0 THEN 1 ELSE 0 END) as critical,
                        SUM(CASE WHEN severity='WARNING' AND resolved=0 THEN 1 ELSE 0 END) as warnings
                    FROM alerts
                ''')
                return dict(cursor.fetchone())
        except Exception as e:
            return {'total': 0, 'active': 0, 'critical': 0, 'warnings': 0}

