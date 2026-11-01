"""
test_system.py — Comprehensive Unit & Integration Test Suite
Smart Traffic Optimization System using AI — 4-Lane Multi-Camera & Dynamic Wait Time
"""

import unittest
import os
import time
import config
from detection.tracker import CentroidTracker
from detection.multi_video_processor import MultiLaneVideoProcessor
from traffic.lane_manager import LaneManager
from traffic.density_engine import DensityEngine
from traffic.signal_controller import SignalController
from database.db_manager import DatabaseManager


class TestTrafficAISystem(unittest.TestCase):
    """Unit tests for core traffic modules."""

    def test_centroid_tracker_registration(self):
        """Test object registration and tracking IDs."""
        tracker = CentroidTracker(max_disappeared=5, max_distance=50)

        # Mock detections in frame 1
        detections_f1 = [
            {'class': 'car', 'confidence': 0.92, 'bbox': [100, 100, 200, 200]},
            {'class': 'bus', 'confidence': 0.88, 'bbox': [350, 50, 450, 150]}
        ]

        tracked_f1 = tracker.update(detections_f1)
        self.assertEqual(len(tracked_f1), 2)
        self.assertEqual(tracker.total_unique_counted, 2)
        self.assertEqual(tracked_f1[0]['id'], 1)
        self.assertEqual(tracked_f1[1]['id'], 2)

    def test_lane_assignment(self):
        """Test quadrant mapping (North, South, East, West)."""
        manager = LaneManager(frame_width=640, frame_height=360)

        self.assertEqual(manager.assign_lane((100, 100)), 'North')
        self.assertEqual(manager.assign_lane((100, 250)), 'South')
        self.assertEqual(manager.assign_lane((400, 100)), 'East')
        self.assertEqual(manager.assign_lane((400, 250)), 'West')

    def test_density_calculation(self):
        """Test PCU weighted density calculations."""
        vehicles = [
            {'class': 'car'},
            {'class': 'car'},
            {'class': 'bus'},        # 2.5 PCU
            {'class': 'motorcycle'}  # 0.5 PCU
        ]
        # Total PCU = 1.0 + 1.0 + 2.5 + 0.5 = 5.0 PCU -> MEDIUM
        res = DensityEngine.calculate_lane_density(vehicles)
        self.assertEqual(res['raw_count'], 4)
        self.assertEqual(res['pcu_score'], 5.0)
        self.assertEqual(res['density_level'], 'MEDIUM')

    def test_signal_controller_timing(self):
        """Test dynamic green time allocation algorithm."""
        controller = SignalController()

        # 0 PCU -> Base green time (15s)
        t_base = controller.calculate_green_time(pcu_score=0.0, vehicle_count=0)
        self.assertEqual(t_base, config.MIN_GREEN_TIME)

        # 10.0 PCU -> 15 + (10 * 2) = 35s
        t_heavy = controller.calculate_green_time(pcu_score=10.0, vehicle_count=8)
        self.assertEqual(t_heavy, 35)

    def test_dynamic_wait_time_calculation(self):
        """Test per-lane dynamic wait time accounting and queue sequencing."""
        controller = SignalController()

        # Mock lane traffic densities
        mock_lanes = {
            'North': {'pcu_score': 0.0, 'raw_count': 0, 'density_level': 'LOW'},
            'East':  {'pcu_score': 5.0, 'raw_count': 3, 'density_level': 'MEDIUM'}, # Green = 15 + 5*2 = 25s
            'South': {'pcu_score': 2.0, 'raw_count': 2, 'density_level': 'LOW'},    # Green = 15 + 2*2 = 19s
            'West':  {'pcu_score': 0.0, 'raw_count': 0, 'density_level': 'LOW'}     # Green = 15s
        }

        # Suppose North is active with 10s remaining
        wait_times, queue_pos = controller.calculate_wait_times(
            active_lane='North',
            remaining_active_sec=10,
            lane_analytics=mock_lanes
        )

        # North (active) has 0 wait time
        self.assertEqual(wait_times['North'], 0)
        self.assertEqual(queue_pos['North'], 0)

        # East has highest density (5.0 PCU) -> Queue #1
        # East wait time = remaining active = 10s
        self.assertEqual(queue_pos['East'], 1)
        self.assertEqual(wait_times['East'], 10)

        # South has second highest density (2.0 PCU) -> Queue #2
        # South wait time = 10s (North) + 25s (East Green) + 3s (Yellow) = 38s
        self.assertEqual(queue_pos['South'], 2)
        self.assertEqual(wait_times['South'], 38)

        # West has lowest density -> Queue #3
        # West wait time = 38s + 19s (South Green) + 3s (Yellow) = 60s
        self.assertEqual(queue_pos['West'], 3)
        self.assertEqual(wait_times['West'], 60)

    def test_emergency_override(self):
        """Test emergency manual override activation and release."""
        controller = SignalController()

        ok, msg = controller.set_manual_override('West', duration=30)
        self.assertTrue(ok)

        state = controller.get_signal_state()
        self.assertTrue(state['override_active'])
        self.assertEqual(state['active_green_lane'], 'West')

        controller.release_manual_override()
        state_released = controller.get_signal_state()
        self.assertFalse(state_released['override_active'])

    def test_multi_video_processor_initialization(self):
        """Test MultiLaneVideoProcessor initialization and lane mapping."""
        processor = MultiLaneVideoProcessor()
        self.assertEqual(len(processor.lanes), 4)
        for lane in ('North', 'East', 'South', 'West'):
            self.assertIn(lane, processor.lanes)
            self.assertEqual(processor.lanes[lane].lane_name, lane)

    def test_database_logging(self):
        """Test SQLite logging and query operations."""
        test_db = os.path.join(config.BASE_DIR, 'tests', 'test_traffic.db')
        if os.path.exists(test_db):
            os.remove(test_db)

        db = DatabaseManager(db_path=test_db)

        mock_snapshot = {
            'total_vehicles': 5,
            'breakdown': {'cars': 3, 'motorcycles': 1, 'buses': 1, 'trucks': 0},
            'lanes': {
                'North': {'count': 2, 'pcu_score': 2.0, 'wait_time': 0},
                'South': {'count': 1, 'pcu_score': 2.5, 'wait_time': 25},
                'East':  {'count': 1, 'pcu_score': 0.5, 'wait_time': 10},
                'West':  {'count': 1, 'pcu_score': 1.0, 'wait_time': 45}
            },
            'active_green_lane': 'North'
        }

        db.log_snapshot(mock_snapshot)
        logs = db.get_recent_logs(limit=10)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]['total_vehicles'], 5)
        self.assertEqual(logs[0]['active_green_lane'], 'North')

    def test_vahan_verification_service(self):
        """Test VAHAN plate syntax validation, RTO resolution, and data structure."""
        from traffic.vahan_service import VahanVerificationService

        # 1. Clean plate helper
        self.assertEqual(VahanVerificationService.clean_plate('DL-01-AB-1234'), 'DL01AB1234')
        self.assertEqual(VahanVerificationService.clean_plate('mh 12 de 1433'), 'MH12DE1433')

        # 2. Syntax validation
        self.assertTrue(VahanVerificationService.validate_syntax('DL01AB1234'))
        self.assertTrue(VahanVerificationService.validate_syntax('KA05MJ9988'))
        self.assertFalse(VahanVerificationService.validate_syntax('INVALID123'))
        self.assertFalse(VahanVerificationService.validate_syntax('12345'))

        # 3. Pre-seeded lookup
        res_seeded = VahanVerificationService.verify_vehicle('DL01AB1234')
        self.assertTrue(res_seeded['success'])
        self.assertEqual(res_seeded['data']['registration_no'], 'DL 01 AB 1234')
        self.assertIn('Hyundai Creta', res_seeded['data']['maker_model'])
        self.assertTrue(res_seeded['data']['insurance_details']['is_active'])

        # 4. Deterministic generated lookup for any plate
        res_gen = VahanVerificationService.verify_vehicle('UP16CD7712')
        self.assertTrue(res_gen['success'])
        self.assertEqual(res_gen['data']['registration_no'], 'UP 16 CD 7712')
        self.assertIn('Noida', res_gen['data']['rto_name'])

        # 5. Invalid plate rejection
        res_err = VahanVerificationService.verify_vehicle('NOT_A_PLATE')
        self.assertFalse(res_err['success'])


if __name__ == '__main__':
    unittest.main()

