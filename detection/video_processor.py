"""
VideoProcessor — Phase 2: OpenCV Video Processing Engine

Responsibilities:
  - Open a traffic video file OR webcam
  - Read frames continuously in a background thread (non-blocking)
  - Store the latest frame in a thread-safe buffer
  - Expose a MJPEG frame generator so Flask can stream to the browser
  - Loop the demo video when it ends (so a demo always keeps running)
  - Handle all errors gracefully (missing file, bad webcam, corrupt frame)
"""

import cv2
import threading
import time
import os
import config


class VideoProcessor:
    """
    Background video reader + MJPEG frame streamer.

    Usage:
        vp = VideoProcessor()
        ok, msg = vp.start('demo')       # or 'webcam'
        # ... later ...
        vp.stop()
    """

    def __init__(self):
        self.capture = None          # OpenCV VideoCapture object
        self.is_running = False      # True while the background thread is active
        self.current_frame = None    # Latest decoded frame (BGR numpy array)
        self.lock = threading.Lock() # Protects current_frame across threads
        self.thread = None           # Background capture thread
        self.source = None           # 'demo' or 'webcam'
        self.video_fps = 30.0        # Source video FPS (read from file/camera)
        self.frame_width = 0
        self.frame_height = 0
        self.error_message = None    # Last error string (None = no error)
        self.frames_read = 0         # Total frames successfully read
        self.detector = None         # Optional VehicleDetector (set in start())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, source='demo', detector=None):
        """
        Open the video source and begin background frame reading.

        Args:
            source (str): 'demo' or 'webcam'
            detector: Optional VehicleDetector instance for YOLO annotation

        Returns:
            (bool, str): (success, message)
        """
        if self.is_running:
            self.stop()

        self.error_message = None
        self.frames_read = 0
        self.detector = detector     # Store the YOLO detector (may be None)

        # Resolve the video path
        if source == 'webcam':
            video_path = 0  # OpenCV interprets integer 0 as camera index 0
        else:
            video_path = config.DEFAULT_VIDEO_PATH
            if not os.path.exists(video_path):
                self.error_message = (
                    f"Demo video not found at: {video_path}\n"
                    f"Place a traffic video named 'traffic.mp4' inside the 'videos/' folder."
                )
                return False, self.error_message

        # Open the source with OpenCV
        self.capture = cv2.VideoCapture(video_path)

        if not self.capture.isOpened():
            self.error_message = (
                "Could not open video source. "
                "Check that the file is a valid video or that your webcam is connected."
            )
            return False, self.error_message

        # Read metadata from the source
        self.video_fps = self.capture.get(cv2.CAP_PROP_FPS)
        if self.video_fps <= 0 or self.video_fps > 120:
            self.video_fps = 30.0   # Fallback for webcams that report 0 FPS

        self.frame_width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.source = source
        self.is_running = True

        # Start the background thread (daemon=True → auto-killed when app exits)
        self.thread = threading.Thread(
            target=self._capture_loop,
            name='VideoCapture-Thread',
            daemon=True
        )
        self.thread.start()

        return True, f"Video capture started — source: {source}"

    def stop(self):
        """Stop the background capture thread and release the camera/file."""
        self.is_running = False

        # Wait for the background thread to finish cleanly (max 2 seconds)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)

        if self.capture:
            self.capture.release()
            self.capture = None

        with self.lock:
            self.current_frame = None

    def get_status(self):
        """Returns a dict describing the current processor state."""
        return {
            'is_running': self.is_running,
            'source': self.source,
            'frames_read': self.frames_read,
            'frame_width': self.frame_width,
            'frame_height': self.frame_height,
            'video_fps': round(self.video_fps, 2),
            'error': self.error_message
        }

    # ------------------------------------------------------------------
    # MJPEG Streaming Generator (used by Flask /video_feed route)
    # ------------------------------------------------------------------

    def generate_frames(self):
        """
        Generator yielding MJPEG multipart frames for Flask streaming.

        The browser's <img> tag can consume this as a continuous stream
        via the 'multipart/x-mixed-replace' content type.
        """
        frame_interval = 1.0 / config.STREAM_FPS

        while self.is_running:
            frame_bytes = self._get_jpeg_frame()

            if frame_bytes is None:
                # No frame yet — send a short pause rather than busy-looping
                time.sleep(0.05)
                continue

            # MJPEG boundary format required by browsers
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n'
                + frame_bytes +
                b'\r\n'
            )

            time.sleep(frame_interval)   # Throttle to STREAM_FPS

    # ------------------------------------------------------------------
    # Private: Background Capture Loop
    # ------------------------------------------------------------------

    def _capture_loop(self):
        """
        Runs in a background thread.
        Continuously reads frames from OpenCV capture and writes to the shared buffer.
        """
        sleep_per_frame = 1.0 / self.video_fps

        while self.is_running:
            if self.capture is None:
                break

            ret, frame = self.capture.read()

            if not ret:
                # Frame read failed — for a demo video, loop back to beginning
                if self.source != 'webcam':
                    self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    # Webcam error — stop
                    self.error_message = "Webcam disconnected or read error."
                    self.is_running = False
                    break

            # Resize to configured resolution for performance
            frame = cv2.resize(
                frame,
                (config.PROCESS_WIDTH, config.PROCESS_HEIGHT),
                interpolation=cv2.INTER_LINEAR
            )

            # Draw the base HUD overlay (timestamp, LIVE badge, frame counter)
            self._draw_hud(frame)

            # --- YOLO Detection (Phase 3) ---
            # If a detector is attached and loaded, run inference on this frame
            if self.detector is not None and self.detector.is_loaded:
                frame, _ = self.detector.detect(frame)

            # Write annotated frame to shared buffer (thread-safe)
            with self.lock:
                self.current_frame = frame
            self.frames_read += 1

            time.sleep(sleep_per_frame)

    def _get_jpeg_frame(self):
        """
        Reads the latest frame from the shared buffer and encodes it as JPEG.
        Returns bytes, or None if no frame is available yet.
        """
        with self.lock:
            if self.current_frame is None:
                return None
            frame = self.current_frame.copy()

        ret, buffer = cv2.imencode(
            '.jpg', frame,
            [cv2.IMWRITE_JPEG_QUALITY, 85]  # 85% quality = good trade-off
        )
        if not ret:
            return None
        return buffer.tobytes()

    def _draw_hud(self, frame):
        """
        Draws a minimal HUD (Heads-Up Display) on the frame so the stream
        looks like an active monitoring feed.
        Phase 3 will replace/extend this with YOLO bounding boxes.
        """
        h, w = frame.shape[:2]

        # Timestamp text
        timestamp = time.strftime('%Y-%m-%d  %H:%M:%S')
        cv2.putText(
            frame, f'TRAFFIC MONITOR  |  {timestamp}',
            org=(10, 24),
            fontFace=cv2.FONT_HERSHEY_SIMPLEX,
            fontScale=0.55,
            color=(0, 255, 180),   # Cyan-green
            thickness=1,
            lineType=cv2.LINE_AA
        )

        # Frame counter (bottom-left)
        cv2.putText(
            frame, f'Frame: {self.frames_read}',
            org=(10, h - 10),
            fontFace=cv2.FONT_HERSHEY_SIMPLEX,
            fontScale=0.45,
            color=(200, 200, 200),
            thickness=1,
            lineType=cv2.LINE_AA
        )

        # "LIVE" badge (top-right corner)
        cv2.rectangle(frame, (w - 70, 6), (w - 6, 30), (0, 0, 200), -1)
        cv2.putText(
            frame, 'LIVE',
            org=(w - 58, 24),
            fontFace=cv2.FONT_HERSHEY_SIMPLEX,
            fontScale=0.55,
            color=(255, 255, 255),
            thickness=1,
            lineType=cv2.LINE_AA
        )
