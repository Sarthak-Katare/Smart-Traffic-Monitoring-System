"""
test_trajectory_and_alerts.py — Tests for City-Wide Intelligence Platform

Covers:
  - DatabaseManager new table operations
  - TrajectoryEngine plate logging and reconstruction
  - AlertEngine blacklist and alert firing
  - AnalyticsEngine heatmap, flow, OD computation
  - New Flask API routes for trajectory, analytics, alerts
"""

import os
import sys
import unittest
import tempfile
import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database.db_manager import DatabaseManager
from traffic.trajectory_engine import TrajectoryEngine, CAMERA_NODES
from traffic.alert_engine import AlertEngine
from traffic.analytics_engine import AnalyticsEngine


def make_test_db():
    """Returns a DatabaseManager backed by a fresh temp SQLite file."""
    tf = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tf.close()
    db = DatabaseManager(db_path=tf.name)
    return db, tf.name


class TestDatabasePlateEvents(unittest.TestCase):
    def setUp(self):
        self.db, self.db_path = make_test_db()

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_log_plate_event(self):
        ok = self.db.log_plate_event('DL01AB1234', 'North', 28.6315, 77.2167, confidence=92.5)
        self.assertTrue(ok)

    def test_get_plate_trajectory_empty(self):
        result = self.db.get_plate_trajectory('UNKNOWN')
        self.assertEqual(result, [])

    def test_get_plate_trajectory_with_data(self):
        self.db.log_plate_event('MH12DE1433', 'North', 28.6315, 77.2167, confidence=88.0)
        self.db.log_plate_event('MH12DE1433', 'East',  28.6280, 77.2410, confidence=91.0)
        result = self.db.get_plate_trajectory('MH12DE1433')
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['camera_id'], 'North')
        self.assertEqual(result[1]['camera_id'], 'East')

    def test_trajectory_plate_normalization(self):
        """Trajectory lookup should match plate with/without spaces."""
        self.db.log_plate_event('DL 01 AB 1234', 'South', 28.5677, 77.2434)
        result = self.db.get_plate_trajectory('DL01AB1234')  # no spaces
        self.assertGreater(len(result), 0)

    def test_recent_plate_events(self):
        for cam in ('North', 'East', 'South'):
            self.db.log_plate_event('KA05MJ9988', cam, 28.6, 77.2)
        events = self.db.get_recent_plate_events(limit=10)
        self.assertEqual(len(events), 3)

    def test_hourly_flow(self):
        self.db.log_plate_event('DL01AB1234', 'North', 28.6315, 77.2167)
        flow = self.db.get_hourly_flow(hours=24)
        # Should have at least 1 row
        self.assertIsInstance(flow, list)

    def test_od_matrix_empty(self):
        result = self.db.get_od_matrix()
        self.assertIsInstance(result, dict)

    def test_od_matrix_with_transitions(self):
        self.db.log_plate_event('HR26DQ5501', 'North', 28.6315, 77.2167)
        self.db.log_plate_event('HR26DQ5501', 'East',  28.6280, 77.2410)
        result = self.db.get_od_matrix()
        self.assertIn('North_TO_East', result)
        self.assertEqual(result['North_TO_East'], 1)


class TestBlacklist(unittest.TestCase):
    def setUp(self):
        self.db, self.db_path = make_test_db()

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_add_to_blacklist(self):
        ok, msg = self.db.add_to_blacklist('DL09XY7799', 'Stolen vehicle', 'Police')
        self.assertTrue(ok)

    def test_is_blacklisted_true(self):
        self.db.add_to_blacklist('DL09XY7799', 'Test')
        self.assertTrue(self.db.is_blacklisted('DL09XY7799'))

    def test_is_blacklisted_false(self):
        self.assertFalse(self.db.is_blacklisted('NOTINLIST'))

    def test_remove_from_blacklist(self):
        self.db.add_to_blacklist('UP16CD7712', 'Test')
        ok, _ = self.db.remove_from_blacklist('UP16CD7712')
        self.assertTrue(ok)
        self.assertFalse(self.db.is_blacklisted('UP16CD7712'))

    def test_get_blacklist(self):
        self.db.add_to_blacklist('MH04TF9001', 'Wanted')
        bl = self.db.get_blacklist()
        self.assertGreater(len(bl), 0)
        plates = [e['plate'] for e in bl]
        self.assertIn('MH04TF9001', plates)

    def test_seed_blacklist_if_empty(self):
        self.db.seed_blacklist_if_empty()
        bl = self.db.get_blacklist()
        self.assertGreaterEqual(len(bl), 3)

    def test_seed_blacklist_idempotent(self):
        self.db.seed_blacklist_if_empty()
        self.db.seed_blacklist_if_empty()  # Should not double-seed
        bl = self.db.get_blacklist()
        self.assertGreaterEqual(len(bl), 3)


class TestAlerts(unittest.TestCase):
    def setUp(self):
        self.db, self.db_path = make_test_db()

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_create_alert(self):
        alert_id = self.db.create_alert('DL01AB1234', 'BLACKLIST_HIT', 'North', 'CRITICAL', 'Test alert')
        self.assertIsNotNone(alert_id)
        self.assertGreater(alert_id, 0)

    def test_get_active_alerts(self):
        self.db.create_alert('TEST01', 'BLACKLIST_HIT', 'East', 'CRITICAL', 'Active')
        alerts = self.db.get_active_alerts()
        self.assertGreater(len(alerts), 0)

    def test_resolve_alert(self):
        aid = self.db.create_alert('TEST02', 'TEST', 'South', 'WARNING', 'To resolve')
        ok = self.db.resolve_alert(aid)
        self.assertTrue(ok)
        active = self.db.get_active_alerts()
        ids = [a['id'] for a in active]
        self.assertNotIn(aid, ids)

    def test_alert_summary(self):
        self.db.create_alert('PL01', 'BLACKLIST_HIT', 'North', 'CRITICAL', '')
        self.db.create_alert('PL02', 'ANOMALY', 'East',  'WARNING',  '')
        summary = self.db.get_alert_summary()
        self.assertIn('total', summary)
        self.assertIn('active', summary)
        self.assertGreaterEqual(summary['total'], 2)


class TestTrajectoryEngine(unittest.TestCase):
    def setUp(self):
        self.db, self.db_path = make_test_db()
        self.engine = TrajectoryEngine(self.db)

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_camera_nodes_returns_all_four(self):
        nodes = self.engine.get_camera_nodes()
        self.assertEqual(len(nodes), 4)
        ids = {n['id'] for n in nodes}
        self.assertSetEqual(ids, {'North', 'East', 'South', 'West'})

    def test_log_sighting_valid_camera(self):
        ok = self.engine.log_sighting('DL01AB1234', 'North', confidence=95.0)
        self.assertTrue(ok)

    def test_log_sighting_invalid_camera(self):
        ok = self.engine.log_sighting('DL01AB1234', 'INVALID_CAM')
        self.assertFalse(ok)

    def test_get_trajectory_not_found(self):
        result = self.engine.get_trajectory('XXXXX')
        self.assertFalse(result['found'])
        self.assertEqual(result['waypoints'], [])

    def test_get_trajectory_found(self):
        self.engine.log_sighting('MH12DE1433', 'North', confidence=90.0, vehicle_class='car')
        self.engine.log_sighting('MH12DE1433', 'East',  confidence=88.5, vehicle_class='car')
        result = self.engine.get_trajectory('MH12DE1433')
        self.assertTrue(result['found'])
        self.assertEqual(len(result['waypoints']), 2)
        self.assertEqual(result['stats']['unique_cameras'], 2)

    def test_trajectory_waypoint_sequence(self):
        for cam in ('North', 'East', 'South'):
            self.engine.log_sighting('KA05MJ9988', cam, confidence=85.0)
        result = self.engine.get_trajectory('KA05MJ9988')
        seqs = [wp['seq'] for wp in result['waypoints']]
        self.assertEqual(seqs, [1, 2, 3])


class TestAlertEngine(unittest.TestCase):
    def setUp(self):
        self.db, self.db_path = make_test_db()
        self.alert_engine = AlertEngine(self.db)
        self.traj_engine  = TrajectoryEngine(self.db)

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_blacklist_seeded_on_init(self):
        """AlertEngine should seed blacklist on first init."""
        bl = self.alert_engine.get_blacklist()
        self.assertGreaterEqual(len(bl), 3)

    def test_check_and_fire_blacklist_hit(self):
        self.alert_engine.add_to_blacklist('DL09XY7799', 'Test suspect')
        alert = self.alert_engine.check_and_fire('DL09XY7799', 'North')
        self.assertIsNotNone(alert)
        self.assertEqual(alert['alert_type'], 'BLACKLIST_HIT')
        self.assertEqual(alert['severity'],   'CRITICAL')

    def test_check_and_fire_clean_plate(self):
        alert = self.alert_engine.check_and_fire('DL01AB1234', 'North')
        # Clean plate should not fire alert (unless anomaly)
        self.assertIsNone(alert)

    def test_rate_limiting(self):
        """Same plate+camera should not fire duplicate alert within cooldown."""
        self.alert_engine.add_to_blacklist('RATETEST1', 'Rate test')
        a1 = self.alert_engine.check_and_fire('RATETEST1', 'East')
        a2 = self.alert_engine.check_and_fire('RATETEST1', 'East')  # Should be rate-limited
        self.assertIsNotNone(a1)
        self.assertIsNone(a2)


class TestAnalyticsEngine(unittest.TestCase):
    def setUp(self):
        self.db, self.db_path = make_test_db()
        self.engine = AnalyticsEngine(self.db)
        # Seed some events
        for cam in ('North', 'East', 'South', 'West'):
            for i in range(5):
                self.db.log_plate_event(f'DL0{i}XX000{i}', cam, 
                    CAMERA_NODES[cam]['lat'], CAMERA_NODES[cam]['lon'], confidence=90.0)

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_heatmap_returns_four_points(self):
        points = self.engine.get_heatmap_data()
        self.assertEqual(len(points), 4)
        for p in points:
            self.assertIn('lat', p)
            self.assertIn('lon', p)
            self.assertIn('intensity', p)
            self.assertGreaterEqual(p['intensity'], 0.0)
            self.assertLessEqual(p['intensity'], 1.0)

    def test_flow_trends_has_24_hours(self):
        data = self.engine.get_flow_trends()
        self.assertEqual(len(data['labels']), 24)
        self.assertEqual(len(data['data']), 24)
        self.assertIn('total_vehicles', data)
        self.assertIn('peak_hour', data)

    def test_od_matrix_structure(self):
        data = self.engine.get_od_matrix()
        self.assertIn('matrix', data)
        self.assertIn('lanes', data)
        self.assertIn('top_routes', data)
        self.assertEqual(len(data['matrix']), 4)

    def test_full_dashboard_keys(self):
        data = self.engine.get_full_dashboard()
        for key in ('heatmap', 'flow_trends', 'od_matrix', 'speed_estimates', 'congestion', 'camera_nodes'):
            self.assertIn(key, data)


class TestNewFlaskRoutes(unittest.TestCase):
    """Integration tests for new API endpoints."""

    def setUp(self):
        # Use a temp DB for Flask app testing
        os.environ['TRAFFIC_DB_PATH'] = tempfile.mktemp(suffix='.db')
        import app as flask_app
        flask_app.app.config['TESTING'] = True
        self.client = flask_app.app.test_client()

    def test_trajectory_page_loads(self):
        r = self.client.get('/trajectory')
        self.assertEqual(r.status_code, 200)

    def test_analytics_page_loads(self):
        r = self.client.get('/analytics')
        self.assertEqual(r.status_code, 200)

    def test_alerts_page_loads(self):
        r = self.client.get('/alerts')
        self.assertEqual(r.status_code, 200)

    def test_api_trajectory_nodes(self):
        r = self.client.get('/api/trajectory/nodes')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['nodes']), 4)

    def test_api_trajectory_not_found(self):
        r = self.client.get('/api/trajectory/XXXXX')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertFalse(data['found'])

    def test_api_analytics_heatmap(self):
        r = self.client.get('/api/analytics/heatmap')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data['success'])

    def test_api_analytics_flow(self):
        r = self.client.get('/api/analytics/flow')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data['success'])

    def test_api_alerts_get(self):
        r = self.client.get('/api/alerts')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data['success'])
        self.assertIn('alerts', data)
        self.assertIn('summary', data)

    def test_api_blacklist_get(self):
        r = self.client.get('/api/blacklist')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data['success'])
        self.assertIn('blacklist', data)

    def test_api_blacklist_add(self):
        r = self.client.post('/api/blacklist/add',
            json={'plate': 'TS10AB1234', 'reason': 'Test plate'})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data['success'])

    def test_api_blacklist_add_no_plate(self):
        r = self.client.post('/api/blacklist/add', json={'reason': 'No plate given'})
        self.assertEqual(r.status_code, 400)

    def test_api_blacklist_remove(self):
        self.client.post('/api/blacklist/add', json={'plate': 'REMOVEME', 'reason': 'Test'})
        r = self.client.delete('/api/blacklist/remove/REMOVEME')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data['success'])

    def test_api_alert_summary(self):
        r = self.client.get('/api/alerts/summary')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn('total', data)
        self.assertIn('active', data)


if __name__ == '__main__':
    unittest.main(verbosity=2)
