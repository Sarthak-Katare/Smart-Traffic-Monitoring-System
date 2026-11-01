"""
detector.py — Phase 4 & 5: YOLO Detection, Centroid Tracking & Multi-Lane Density Engine

Integrates:
  - YOLOv8 Vehicle Object Detection
  - Centroid Object Tracker (persistent vehicle IDs across frames)
  - LaneManager (4 intersection ROI regions: North, South, East, West)
  - DensityEngine (PCU weighted traffic density calculations)
"""

import cv2
import config
from detection.tracker import CentroidTracker
from traffic.lane_manager import LaneManager
from traffic.density_engine import DensityEngine

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except (ImportError, Exception, OSError):
    YOLO_AVAILABLE = False

VEHICLE_STYLE = {
    'car':        {'display': 'Car',        'color': (255, 120,  50)},   # Orange
    'motorcycle': {'display': 'Motorcycle', 'color': ( 50, 220, 100)},   # Green
    'bus':        {'display': 'Bus',        'color': ( 50, 200, 255)},   # Amber
    'truck':      {'display': 'Truck',      'color': ( 60,  60, 255)},   # Red
}


class VehicleDetector:
    """
    Combines YOLOv8 detection, Centroid tracking, and Lane density analysis into a unified engine.
    """

    def __init__(self):
        self.model = None
        self.is_loaded = False
        self.error_message = None

        # Tracking & Lane modules
        self.tracker = CentroidTracker(max_disappeared=15, max_distance=60)
        self.lane_manager = LaneManager(config.PROCESS_WIDTH, config.PROCESS_HEIGHT)

        # Last analyzed results — shared with Flask APIs
        self.last_detections = []       # Raw YOLO detections
        self.last_tracked_objects = []  # Tracked objects with IDs
        self.last_lane_analytics = {}   # Per-lane count, PCU, density levels

        # Frame skip for CPU optimization
        self._frame_counter = 0
        self._detect_every = 2

    def load_model(self):
        """Loads YOLOv8n model weights."""
        if not YOLO_AVAILABLE:
            self.error_message = "ultralytics package not installed."
            return False, self.error_message

        try:
            print(f"[YOLO] Loading model: {config.MODEL_NAME} ...")
            self.model = YOLO(config.MODEL_NAME)
            self.is_loaded = True
            print("[YOLO] Model loaded successfully.")
            return True, "YOLOv8n loaded — ready for vehicle detection & tracking"
        except Exception as e:
            self.error_message = f"Model load failed: {str(e)}"
            return False, self.error_message

    def detect(self, frame):
        """
        Runs detection, tracking, and lane analysis on the BGR frame.

        Returns:
            annotated_frame (BGR numpy array)
            tracked_objects (list of dicts)
        """
        if not self.is_loaded or self.model is None:
            return frame, []

        self._frame_counter += 1

        # Frame-skipping for CPU efficiency
        if self._frame_counter % self._detect_every != 0:
            annotated = self._render_frame_annotations(frame.copy(), self.last_tracked_objects)
            return annotated, self.last_tracked_objects

        try:
            # --- 1. YOLO Inference ---
            results = self.model(
                frame,
                imgsz=320,
                conf=config.CONFIDENCE_THRESHOLD,
                verbose=False
            )

            raw_detections = []
            res = results[0]

            for box in res.boxes:
                class_id = int(box.cls[0])
                class_name = res.names[class_id]

                if class_name not in config.TARGET_VEHICLE_CLASSES:
                    continue

                confidence = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])

                raw_detections.append({
                    'class': class_name,
                    'confidence': round(confidence, 3),
                    'bbox': [x1, y1, x2, y2]
                })

            self.last_detections = raw_detections

            # --- 2. Centroid Tracking ---
            tracked_objects = self.tracker.update(raw_detections)
            self.last_tracked_objects = tracked_objects

            # --- 3. Lane Region Classification & Density ---
            classified_lanes = self.lane_manager.classify_vehicles_by_lane(tracked_objects)
            self.last_lane_analytics = DensityEngine.analyze_all_lanes(classified_lanes)

            # --- 4. Render Annotations ---
            annotated = self._render_frame_annotations(frame.copy(), tracked_objects)
            return annotated, tracked_objects

        except Exception as e:
            print(f"[YOLO] Detection error: {e}")
            return frame, self.last_tracked_objects

    def _render_frame_annotations(self, frame, tracked_objects):
        """
        Draws ROI grid lines, vehicle bounding boxes with track IDs, and HUD.
        """
        # Draw Lane ROI dividing lines and text labels
        frame = self.lane_manager.draw_lane_overlays(frame)

        # Draw vehicle bounding boxes with ID
        for obj in tracked_objects:
            obj_id = obj['id']
            cls = obj['class']
            conf = obj['confidence']
            x1, y1, x2, y2 = obj['bbox']

            style = VEHICLE_STYLE.get(cls, {'display': cls.capitalize(), 'color': (200, 200, 200)})
            color = style['color']
            display = style['display']

            # Bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            # Center point marker
            cx, cy = obj['centroid']
            cv2.circle(frame, (cx, cy), 3, (0, 255, 255), -1)

            # Label text: "#3 Car 91%"
            label = f"#{obj_id} {display} {int(conf * 100)}%"
            (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)

            label_x1 = x1
            label_y1 = max(y1 - text_h - 6, 0)
            label_x2 = x1 + text_w + 6
            label_y2 = y1

            cv2.rectangle(frame, (label_x1, label_y1), (label_x2, label_y2), color, -1)
            cv2.putText(
                frame, label,
                (x1 + 3, y1 - 3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                (10, 10, 10), 1, cv2.LINE_AA
            )

        # Top summary overlay
        counts = self.get_counts()
        summary = (
            f"Active: {len(tracked_objects)} | "
            f"Total Counted: {self.tracker.total_unique_counted} | "
            f"C:{counts['cars']} B:{counts['motorcycles']} Bus:{counts['buses']} T:{counts['trucks']}"
        )
        cv2.putText(
            frame, summary,
            (10, 46),
            cv2.FONT_HERSHEY_SIMPLEX, 0.44,
            (0, 255, 180), 1, cv2.LINE_AA
        )

        return frame

    def get_counts(self):
        """Returns vehicle breakdown for currently tracked objects."""
        counts = {'cars': 0, 'motorcycles': 0, 'buses': 0, 'trucks': 0}
        for obj in self.last_tracked_objects:
            cls = obj['class']
            if   cls == 'car':        counts['cars']        += 1
            elif cls == 'motorcycle': counts['motorcycles'] += 1
            elif cls == 'bus':        counts['buses']       += 1
            elif cls == 'truck':      counts['trucks']      += 1
        return counts

    def get_total(self):
        """Active vehicles currently tracked."""
        return len(self.last_tracked_objects)

    def get_lifetime_total(self):
        """Total unique vehicles counted since session start."""
        return self.tracker.total_unique_counted

    def get_lane_analytics(self):
        """Returns per-lane counts, PCU scores, and density levels."""
        return self.last_lane_analytics

    def get_status(self):
        return {
            'yolo_available': YOLO_AVAILABLE,
            'model_loaded':   self.is_loaded,
            'model_name':     config.MODEL_NAME,
            'error':          self.error_message,
            'active_tracked': len(self.last_tracked_objects),
            'lifetime_unique': self.tracker.total_unique_counted
        }
