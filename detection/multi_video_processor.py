"""
multi_video_processor.py — Multi-Lane 4-Camera Video Capture & AI Inference Engine

Manages 4 independent video streams for North, East, South, and West intersection lanes.
Performs concurrent YOLOv8 vehicle detection, Centroid tracking, and PCU density analysis
for each lane individually, providing dedicated per-lane MJPEG streams and a combined 2x2 Quad-View.
"""

import os
import time
import threading
import collections
import cv2
import numpy as np
import config
from detection.tracker import CentroidTracker
from traffic.density_engine import DensityEngine
from detection.anpr_detector import ANPRDetector

LANE_NAMES = ['North', 'East', 'South', 'West']

LANE_COLORS = {
    'North': (255, 180,   0),   # Cyan
    'East':  (100, 220,  50),   # Emerald Green
    'South': ( 50, 200, 255),   # Amber/Orange
    'West':  (200,  80, 255)    # Purple/Pink
}

VEHICLE_STYLE = {
    'car':        {'display': 'Car',        'color': (255, 120,  50)},   # Orange
    'motorcycle': {'display': 'Motorcycle', 'color': ( 50, 220, 100)},   # Green
    'bus':        {'display': 'Bus',        'color': ( 50, 200, 255)},   # Amber
    'truck':      {'display': 'Truck',      'color': ( 60,  60, 255)},   # Red
}


def is_live_source(source):
    """Checks if a video source is a live webcam index or network stream."""
    if isinstance(source, int):
        return True
    if isinstance(source, str):
        s = source.strip()
        if s.isdigit():
            return True
        if s.startswith(('rtsp://', 'http://', 'https://')):
            return True
    return False


def open_capture_device(source):
    """Opens cv2.VideoCapture for a file, camera index, or live URL."""
    if isinstance(source, int) or (isinstance(source, str) and source.strip().isdigit()):
        cam_idx = int(source)
        cap = cv2.VideoCapture(cam_idx, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(cam_idx)
        return cap
    elif isinstance(source, str) and source.startswith(('rtsp://', 'http://', 'https://')):
        return cv2.VideoCapture(source)
    else:
        return cv2.VideoCapture(source)


class LaneStream:
    """Represents a single lane's video stream, tracker, and metrics."""

    def __init__(self, lane_name, default_path):
        self.lane_name = lane_name
        self.source_path = default_path
        self.is_live = is_live_source(default_path)
        self.capture = None
        self.current_frame = None
        self.lock = threading.Lock()
        self.fps = 25.0
        self.frames_read = 0
        self.is_active = False
        self.error_message = None

        # Dedicated tracker per lane for independent ID tracking
        self.tracker = CentroidTracker(max_disappeared=15, max_distance=60)
        self.tracked_objects = []
        self.lane_analytics = {
            'raw_count': 0,
            'pcu_score': 0.0,
            'density_level': 'LOW',
            'breakdown': {'cars': 0, 'motorcycles': 0, 'buses': 0, 'trucks': 0}
        }

        # ANPR: rolling deque of last 10 detected plates for this lane
        self.detected_plates = collections.deque(maxlen=10)
        self.last_anpr_frame = 0


class MultiLaneVideoProcessor:
    """
    Orchestrates 4 individual video capture streams and runs YOLO inference per lane.
    """

    def __init__(self, detector=None, trajectory_engine=None, alert_engine=None):
        self.detector = detector
        self.anpr = ANPRDetector()    # Shared ANPR engine across all 4 lanes
        self.trajectory_engine = trajectory_engine  # NEW: city-wide trajectory logger
        self.alert_engine = alert_engine            # NEW: real-time alert engine
        self.is_running = False
        self.thread = None
        self.lanes = {}

        for name in LANE_NAMES:
            default_file = config.LANE_VIDEO_PATHS.get(name, config.DEFAULT_VIDEO_PATH)
            self.lanes[name] = LaneStream(name, default_file)

        self._frame_counter = 0
        self._detect_every = 2  # Run YOLO every N frames per lane for smooth CPU performance

    def set_detector(self, detector):
        self.detector = detector

    def set_lane_source(self, lane_name, source_path):
        """Changes the video file / webcam / live stream for a specific lane."""
        if lane_name not in self.lanes:
            return False, f"Unknown lane: {lane_name}"

        # Convert numeric string to integer camera index if applicable
        if isinstance(source_path, str) and source_path.strip().isdigit():
            source_path = int(source_path.strip())

        lane = self.lanes[lane_name]
        with lane.lock:
            lane.source_path = source_path
            lane.is_live = is_live_source(source_path)
            if self.is_running:
                # Reopen capture
                if lane.capture is not None:
                    lane.capture.release()
                lane.capture = open_capture_device(source_path)
                if not lane.capture.isOpened():
                    disp = f"Camera {source_path}" if isinstance(source_path, int) else str(source_path)
                    lane.error_message = f"Could not connect to source: {disp}"
                    return False, lane.error_message
                lane.error_message = None
                fps = lane.capture.get(cv2.CAP_PROP_FPS)
                lane.fps = fps if (fps > 0 and fps <= 120) else 25.0
                lane.frames_read = 0

        source_display = f"Webcam {source_path}" if isinstance(source_path, int) else os.path.basename(str(source_path))
        return True, f"Updated video source for {lane_name} Lane to {source_display}."

    def start(self, sources=None):
        """
        Starts capture threads for all 4 lanes.
        sources: Optional dict {'North': path, 'East': path, 'South': path, 'West': path}
        """
        if self.is_running:
            self.stop()

        if sources:
            for name, path in sources.items():
                if name in self.lanes:
                    self.lanes[name].source_path = path

        # Open captures for all lanes
        for name, lane in self.lanes.items():
            path = lane.source_path
            lane.is_live = is_live_source(path)
            if not lane.is_live:
                if isinstance(path, str) and not os.path.exists(path):
                    # Fallback to default video
                    path = config.DEFAULT_VIDEO_PATH
                    lane.source_path = path

            lane.capture = open_capture_device(path)
            if not lane.capture.isOpened():
                lane.error_message = f"Failed to open {path}"
                print(f"[MULTI-VIDEO] Warning: Failed to open {name} stream ({path})")
            else:
                lane.error_message = None
                fps = lane.capture.get(cv2.CAP_PROP_FPS)
                lane.fps = fps if (fps > 0 and fps <= 120) else 25.0
                lane.frames_read = 0

        self.is_running = True
        self.thread = threading.Thread(target=self._capture_loop, name='MultiLaneCaptureThread', daemon=True)
        self.thread.start()
        print("[MULTI-VIDEO] Started 4-Lane Multi-Camera Video Processor.")
        return True, "4-Lane video processor started successfully."

    def stop(self):
        """Stops all video streams cleanly."""
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

        for name, lane in self.lanes.items():
            if lane.capture:
                lane.capture.release()
                lane.capture = None
            with lane.lock:
                lane.current_frame = None

        print("[MULTI-VIDEO] Stopped all lane video streams.")

    def _capture_loop(self):
        """Background loop reading and processing frames for all 4 lanes."""
        target_w = config.PROCESS_WIDTH
        target_h = config.PROCESS_HEIGHT

        while self.is_running:
            self._frame_counter += 1
            run_yolo = (self._frame_counter % self._detect_every == 0) and (self.detector and self.detector.is_loaded)

            for name, lane in self.lanes.items():
                if lane.capture is None or not lane.capture.isOpened():
                    continue

                ret, frame = lane.capture.read()
                if not ret:
                    if lane.is_live:
                        time.sleep(0.05)
                        continue
                    # Loop video back to start
                    lane.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = lane.capture.read()
                    if not ret:
                        continue

                frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

                # Process YOLO Detection on this lane frame
                if run_yolo:
                    tracked_objs, lane_analytics = self._process_lane_frame(lane, frame)
                    lane.tracked_objects = tracked_objs
                    lane.lane_analytics = lane_analytics

                # Render Annotations & Lane HUD
                annotated = self._render_lane_hud(frame.copy(), lane)

                with lane.lock:
                    lane.current_frame = annotated
                    lane.frames_read += 1

            time.sleep(1.0 / config.STREAM_FPS)

    def _process_lane_frame(self, lane, frame):
        """Runs YOLO on a lane's frame and updates its CentroidTracker, PCU metrics, and ANPR."""
        try:
            results = self.detector.model(
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

            # Update lane-specific tracker
            tracked_objs = lane.tracker.update(raw_detections)

            # Calculate density & PCU for this lane
            lane_analytics = DensityEngine.calculate_lane_density(tracked_objs)

            # ── ANPR: scan for plates using YOLO vehicle boxes as hints ──
            if self.anpr.is_ready:
                vehicle_boxes = [{'bbox': d['bbox'], 'class': d['class']} for d in raw_detections]
                new_plates = self.anpr.process_frame(frame, vehicle_boxes)
                for p in new_plates:
                    p['lane'] = lane.lane_name
                    lane.detected_plates.appendleft(p)

                    # ── NEW: Log to trajectory system + check alerts ──
                    plate_text = p.get('plate', '')
                    if plate_text:
                        if self.trajectory_engine:
                            try:
                                self.trajectory_engine.log_sighting(
                                    plate=plate_text,
                                    camera_id=lane.lane_name,
                                    confidence=p.get('confidence', 0.0),
                                    vehicle_class=p.get('vehicle_class', 'unknown'),
                                )
                            except Exception:
                                pass
                        if self.alert_engine:
                            try:
                                self.alert_engine.check_and_fire(
                                    plate=plate_text,
                                    camera_id=lane.lane_name,
                                )
                            except Exception:
                                pass

            return tracked_objs, lane_analytics

        except Exception as e:
            print(f"[MULTI-VIDEO] Inference error on {lane.lane_name}: {e}")
            return lane.tracked_objects, lane.lane_analytics

    def _render_lane_hud(self, frame, lane):
        """Draws bounding boxes, lane badge, and HUD info on a lane's frame."""
        h, w = frame.shape[:2]
        lane_color = LANE_COLORS.get(lane.lane_name, (0, 255, 255))

        # 1. Draw vehicle bounding boxes
        for obj in lane.tracked_objects:
            obj_id = obj['id']
            cls = obj['class']
            conf = obj['confidence']
            x1, y1, x2, y2 = obj['bbox']

            style = VEHICLE_STYLE.get(cls, {'display': cls.capitalize(), 'color': (200, 200, 200)})
            box_color = style['color']
            display = style['display']

            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
            cx, cy = obj['centroid']
            cv2.circle(frame, (cx, cy), 3, (0, 255, 255), -1)

            label = f"#{obj_id} {display} {int(conf * 100)}%"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)

            cv2.rectangle(frame, (x1, max(y1 - th - 6, 0)), (x1 + tw + 6, y1), box_color, -1)
            cv2.putText(frame, label, (x1 + 3, y1 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (10, 10, 10), 1, cv2.LINE_AA)

        # 2. Draw Top Lane Banner
        cv2.rectangle(frame, (0, 0), (w, 32), (15, 23, 42), -1)
        cv2.line(frame, (0, 32), (w, 32), lane_color, 2)

        lane_title = f"{lane.lane_name.upper()} CAMERA | {lane.lane_analytics['raw_count']} Vehicles ({lane.lane_analytics['pcu_score']} PCU)"
        cv2.putText(frame, lane_title, (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52, lane_color, 2, cv2.LINE_AA)

        # LIVE Badge
        cv2.rectangle(frame, (w - 65, 6), (w - 10, 26), (0, 0, 200), -1)
        cv2.putText(frame, "LIVE", (w - 55, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

        # Bottom Breakdown Bar
        b = lane.lane_analytics['breakdown']
        summary = f"C:{b['cars']} | M:{b['motorcycles']} | B:{b['buses']} | T:{b['trucks']} | Density: {lane.lane_analytics['density_level']}"
        cv2.rectangle(frame, (0, h - 24), (w, h), (15, 23, 42), -1)
        cv2.putText(frame, summary, (10, h - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (200, 200, 200), 1, cv2.LINE_AA)

        # Draw ANPR plate labels under detected vehicle boxes
        if lane.detected_plates:
            ANPRDetector.draw_plates_on_frame(frame, list(lane.detected_plates)[:3])

        return frame

    # ----------------------------------------------------------------------
    # Stream Generators
    # ----------------------------------------------------------------------

    def generate_lane_frames(self, lane_name):
        """Yields MJPEG stream for a specific lane."""
        frame_interval = 1.0 / config.STREAM_FPS
        lane = self.lanes.get(lane_name)

        while self.is_running and lane is not None:
            with lane.lock:
                frame = lane.current_frame.copy() if lane.current_frame is not None else None

            if frame is None:
                time.sleep(0.05)
                continue

            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ret:
                continue

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n'
                + buffer.tobytes() +
                b'\r\n'
            )
            time.sleep(frame_interval)

    def generate_composite_frames(self):
        """
        Yields 2x2 Composite Quad-View MJPEG stream (North, East, South, West).
        """
        frame_interval = 1.0 / config.STREAM_FPS
        half_w = config.PROCESS_WIDTH // 2
        half_h = config.PROCESS_HEIGHT // 2

        blank_half = np.zeros((half_h, half_w, 3), dtype=np.uint8)

        while self.is_running:
            quad_frames = []
            for name in ('North', 'East', 'South', 'West'):
                lane = self.lanes[name]
                with lane.lock:
                    f = lane.current_frame.copy() if lane.current_frame is not None else None

                if f is not None:
                    resized = cv2.resize(f, (half_w, half_h), interpolation=cv2.INTER_LINEAR)
                    quad_frames.append(resized)
                else:
                    quad_frames.append(blank_half.copy())

            # Arrange: Top Row (North, East), Bottom Row (South, West)
            top_row = np.hstack((quad_frames[0], quad_frames[1]))
            bot_row = np.hstack((quad_frames[2], quad_frames[3]))
            composite = np.vstack((top_row, bot_row))

            ret, buffer = cv2.imencode('.jpg', composite, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ret:
                time.sleep(0.05)
                continue

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n'
                + buffer.tobytes() +
                b'\r\n'
            )
            time.sleep(frame_interval)

    # ----------------------------------------------------------------------
    # Analytics & Aggregates
    # ----------------------------------------------------------------------

    def get_lane_analytics_all(self):
        """Returns per-lane density metrics dictionary for all 4 lanes."""
        return {name: lane.lane_analytics for name, lane in self.lanes.items()}

    def get_total_vehicles(self):
        """Active total vehicles across all 4 lanes."""
        return sum(len(lane.tracked_objects) for lane in self.lanes.values())

    def get_lifetime_total(self):
        """Lifetime unique vehicles counted across all 4 lanes."""
        return sum(lane.tracker.total_unique_counted for lane in self.lanes.values())

    def get_breakdown(self):
        """Aggregate breakdown across all 4 lanes."""
        total_breakdown = {'cars': 0, 'motorcycles': 0, 'buses': 0, 'trucks': 0}
        for lane in self.lanes.values():
            b = lane.lane_analytics.get('breakdown', {})
            for k in total_breakdown:
                total_breakdown[k] += b.get(k, 0)
        return total_breakdown

    def get_status(self):
        """Status for all 4 lane video feeds."""
        lanes_status = {}
        for name, lane in self.lanes.items():
            if isinstance(lane.source_path, int):
                src_disp = f"Webcam {lane.source_path}"
            elif isinstance(lane.source_path, str):
                if lane.source_path.startswith(('rtsp://', 'http://', 'https://')):
                    src_disp = lane.source_path
                else:
                    src_disp = os.path.basename(lane.source_path)
            else:
                src_disp = str(lane.source_path) if lane.source_path is not None else 'None'

            lanes_status[name] = {
                'source': src_disp,
                'is_live': lane.is_live,
                'frames_read': lane.frames_read,
                'active_vehicles': len(lane.tracked_objects),
                'error': lane.error_message
            }
        return {
            'is_running': self.is_running,
            'lanes': lanes_status
        }

    def get_all_detected_plates(self):
        """Returns all recently detected plates across all 4 lanes (for the Live ANPR Log)."""
        all_plates = []
        for name, lane in self.lanes.items():
            for plate in lane.detected_plates:
                entry = dict(plate)
                entry['lane'] = name
                all_plates.append(entry)
        # Sort by timestamp descending (string HH:MM:SS sort works within same day)
        all_plates.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return all_plates[:20]

    def get_best_current_frame(self, lane_name=None):
        """Returns the latest raw frame for a given lane (or any active lane) for ANPR scan."""
        if lane_name and lane_name in self.lanes:
            lane = self.lanes[lane_name]
            with lane.lock:
                return lane.current_frame.copy() if lane.current_frame is not None else None

        # Return first non-None frame
        for lane in self.lanes.values():
            with lane.lock:
                if lane.current_frame is not None:
                    return lane.current_frame.copy()
        return None
