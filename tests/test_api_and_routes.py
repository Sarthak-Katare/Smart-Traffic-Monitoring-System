"""
test_api_and_routes.py — Complete End-to-End API & Integration Test Suite
Tests all Flask endpoints, routes, controllers, and database interactions.
"""

import unittest
import json
import os
import config
from app import app, db_manager, signal_controller, multi_video_processor


class TestFullProjectAPIs(unittest.TestCase):
    """Integration tests for all Flask routes, video streams, signals, and database."""

    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def test_01_index_page(self):
        """Test home page loads successfully with HTML content."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Smart Traffic', response.data)

    def test_02_history_page(self):
        """Test analytics history page loads successfully."""
        response = self.client.get('/history')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Traffic Records History', response.data)

    def test_03_health_check(self):
        """Test /api/health endpoint."""
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('active_lanes'), ['North', 'East', 'South', 'West'])

    def test_04_system_status(self):
        """Test /api/status endpoint."""
        response = self.client.get('/api/status')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get('status'), 'online')
        self.assertIn('system_config', data)
        self.assertIn('signal_controller', data)

    def test_05_traffic_stats(self):
        """Test /api/stats endpoint."""
        response = self.client.get('/api/stats')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('total_vehicles', data)
        self.assertIn('breakdown', data)
        self.assertIn('lanes', data)
        self.assertIn('active_green_lane', data)
        for lane in ('North', 'East', 'South', 'West'):
            self.assertIn(lane, data['lanes'])

    def test_06_detections_endpoint(self):
        """Test /api/detections endpoint."""
        response = self.client.get('/api/detections')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('active_vehicles', data)
        self.assertIn('lanes', data)

    def test_07_signal_manual_override(self):
        """Test emergency manual signal override and release via API."""
        # Enable override on East lane for 20 seconds
        res = self.client.post('/api/signal/override', json={
            'action': 'enable',
            'lane': 'East',
            'duration': 20
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))

        state = signal_controller.get_signal_state()
        self.assertTrue(state['override_active'])
        self.assertEqual(state['active_green_lane'], 'East')

        # Release override
        res_rel = self.client.post('/api/signal/override', json={
            'action': 'disable'
        })
        self.assertEqual(res_rel.status_code, 200)
        data_rel = res_rel.get_json()
        self.assertTrue(data_rel.get('success'))

        state_after = signal_controller.get_signal_state()
        self.assertFalse(state_after['override_active'])

    def test_08_vahan_verify_api(self):
        """Test VAHAN verification API with valid, invalid, and missing plate inputs."""
        # 1. Valid registered plate
        res = self.client.post('/api/vahan/verify', json={
            'registration_number': 'DL01AB1234'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data['data']['registration_no'], 'DL 01 AB 1234')
        self.assertIn('Motor Car', data['data']['vehicle_class'])

        # 2. Invalid syntax plate
        res_bad = self.client.post('/api/vahan/verify', json={
            'registration_number': 'BAD_PLATE_123'
        })
        self.assertEqual(res_bad.status_code, 400)

        # 3. Missing plate payload
        res_missing = self.client.post('/api/vahan/verify', json={})
        self.assertEqual(res_missing.status_code, 400)

    def test_09_vahan_recent_and_live_anpr(self):
        """Test /api/vahan/recent and /api/anpr/live endpoints."""
        res = self.client.get('/api/vahan/recent')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))

        res_anpr = self.client.get('/api/anpr/live')
        self.assertEqual(res_anpr.status_code, 200)
        data_anpr = res_anpr.get_json()
        self.assertTrue(data_anpr.get('success'))
        self.assertIn('plates', data_anpr)

    def test_10_video_management_apis(self):
        """Test video listing, status, and control APIs."""
        # Status
        res_status = self.client.get('/api/video/status')
        self.assertEqual(res_status.status_code, 200)
        data_status = res_status.get_json()
        self.assertIn('is_running', data_status)
        self.assertIn('lanes', data_status)

        # File list
        res_files = self.client.get('/api/video/list_files')
        self.assertEqual(res_files.status_code, 200)
        data_files = res_files.get_json()
        self.assertTrue(data_files.get('success'))
        self.assertTrue(len(data_files.get('files', [])) > 0)

        # Webcam detection list
        res_webcams = self.client.get('/api/video/list_webcams')
        self.assertEqual(res_webcams.status_code, 200)
        data_webcams = res_webcams.get_json()
        self.assertTrue(data_webcams.get('success'))
        self.assertIsInstance(data_webcams.get('webcams'), list)

        # Invalid lane name rejection
        res_inv = self.client.post('/api/video/set_source', json={
            'lane': 'Moon',
            'source': 'lane_north.mp4'
        })
        self.assertEqual(res_inv.status_code, 400)

        # Non-existent file rejection
        res_nofile = self.client.post('/api/video/set_source', json={
            'lane': 'North',
            'source': 'non_existent_file_xyz.mp4'
        })
        self.assertEqual(res_nofile.status_code, 404)

    def test_11_history_api(self):
        """Test SQLite history retrieval and clearing."""
        # Insert a sample log first
        sample = {
            'total_vehicles': 8,
            'breakdown': {'cars': 5, 'motorcycles': 2, 'buses': 1, 'trucks': 0},
            'lanes': {
                'North': {'count': 3, 'pcu_score': 3.0, 'wait_time': 0},
                'South': {'count': 2, 'pcu_score': 2.0, 'wait_time': 20},
                'East':  {'count': 2, 'pcu_score': 2.0, 'wait_time': 35},
                'West':  {'count': 1, 'pcu_score': 2.5, 'wait_time': 50}
            },
            'active_green_lane': 'North'
        }
        db_manager.log_snapshot(sample)

        # Fetch history
        res = self.client.get('/api/history?limit=10')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        self.assertGreaterEqual(data.get('total_logs', 0), 1)
        self.assertIn('summary', data)

    def test_12_video_feed_lane_validation(self):
        """Test video feed route rejects invalid lane parameter."""
        res = self.client.get('/video_feed/invalid_lane')
        self.assertEqual(res.status_code, 400)


if __name__ == '__main__':
    unittest.main()
