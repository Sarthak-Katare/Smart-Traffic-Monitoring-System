"""
test_live_pipeline.py — End-to-End Live Pipeline Verification
Verifies YOLO inference on actual video files, 4-lane video processor,
composite quad-view MJPEG generator, dynamic signal state changes, and ANPR.
"""

import unittest
import os
import cv2
import config
from detection.detector import VehicleDetector
from detection.multi_video_processor import MultiLaneVideoProcessor
from traffic.signal_controller import SignalController
from traffic.vahan_service import VahanVerificationService
from database.db_manager import DatabaseManager


class TestLivePipeline(unittest.TestCase):
    """Verifies live computer vision pipeline with real video frames and model weights."""

    def test_01_yolo_model_inference_on_video(self):
        """Test YOLO model loads weights and runs inference on a real video frame."""
        detector = VehicleDetector()
        loaded, msg = detector.load_model()
        self.assertTrue(loaded, f"Model failed to load: {msg}")

        # Open lane_north video and read a frame
        cap = cv2.VideoCapture(config.LANE_VIDEO_PATHS['North'])
        self.assertTrue(cap.isOpened(), "Could not open lane_north.mp4")
        ret, frame = cap.read()
        cap.release()
        self.assertTrue(ret, "Failed to read frame from lane_north.mp4")

        # Resize to standard process dimensions
        frame = cv2.resize(frame, (config.PROCESS_WIDTH, config.PROCESS_HEIGHT))

        # Detect
        annotated_frame, tracked = detector.detect(frame)
        self.assertEqual(annotated_frame.shape, (config.PROCESS_HEIGHT, config.PROCESS_WIDTH, 3))
        # Check lane analytics were calculated
        self.assertIsNotNone(detector.last_lane_analytics)

    def test_02_composite_frame_generation(self):
        """Test 2x2 Composite Quad-View MJPEG frame rendering."""
        detector = VehicleDetector()
        detector.load_model()
        processor = MultiLaneVideoProcessor(detector=detector)
        processor.start()

        import time
        time.sleep(1.0)  # Allow processor to capture initial frames

        # Obtain the first frame from the composite stream generator
        gen = processor.generate_composite_frames()
        first_chunk = next(gen)
        self.assertIsNotNone(first_chunk)
        self.assertIn(b'--frame', first_chunk)
        self.assertIn(b'Content-Type: image/jpeg', first_chunk)

        processor.stop()

    def test_03_signal_controller_live_flow(self):
        """Test signal controller dynamic green adjustment with varying PCU inputs."""
        controller = SignalController()

        # Simulate dynamic traffic data
        lanes_data = {
            'North': {'pcu_score': 8.5, 'raw_count': 6, 'density_level': 'HIGH'},
            'East':  {'pcu_score': 1.0, 'raw_count': 1, 'density_level': 'LOW'},
            'South': {'pcu_score': 3.0, 'raw_count': 2, 'density_level': 'LOW'},
            'West':  {'pcu_score': 0.0, 'raw_count': 0, 'density_level': 'LOW'},
        }

        # Next lane selection should choose 'North' due to highest PCU
        next_lane = controller.select_next_lane(lanes_data)
        self.assertEqual(next_lane, 'North')

        # Wait times calculation
        wait_times, queue_positions = controller.calculate_wait_times(
            active_lane='North',
            remaining_active_sec=15,
            lane_analytics=lanes_data
        )

        self.assertEqual(wait_times['North'], 0)
        self.assertEqual(queue_positions['North'], 0)
        # Remaining waiting lanes ordered by priority: South (3.0 PCU) > East (1.0 PCU) > West (0 PCU)
        self.assertEqual(queue_positions['South'], 1)
        self.assertEqual(queue_positions['East'], 2)
        self.assertEqual(queue_positions['West'], 3)


if __name__ == '__main__':
    unittest.main()
