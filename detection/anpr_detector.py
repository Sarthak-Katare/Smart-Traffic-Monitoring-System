"""
anpr_detector.py -- Automatic Number Plate Recognition (ANPR) Engine

Pipeline:
  1. For each vehicle bounding box (from YOLO), crop the lower half where plates appear
  2. Apply bilateral filter -> grayscale -> Canny edge detection -> morphological ops
  3. Find rectangular contours (plate-shaped aspect ratio)
  4. Pass plate crop to EasyOCR for character recognition
  5. Filter OCR output against Indian plate syntax regex
  6. Return list of (plate_text, confidence, bbox) tuples

Falls back to full-frame scan if no vehicle boxes are provided.
EasyOCR reader is loaded lazily on first call (shared singleton, thread-safe).
"""

import re
import threading
import time
import cv2
import numpy as np

# Indian plate regex: DL01AB1234 / KA05MJ9988 / MH12DE1433 etc.
PLATE_REGEX = re.compile(
    r'\b([A-Z]{2})\s*([0-9]{1,2})\s*([A-Z]{1,3})\s*([0-9]{4})\b'
)

_reader_lock = threading.Lock()
_reader = None
_reader_loading = False


def _get_reader():
    """Return the shared EasyOCR reader (loaded once, thread-safe)."""
    global _reader, _reader_loading
    if _reader is not None:
        return _reader
    with _reader_lock:
        if _reader is not None:
            return _reader
        _reader_loading = True
        try:
            import easyocr
            print("[ANPR] Loading EasyOCR model (first time -- may take ~20s)...")
            _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            print("[ANPR] EasyOCR model loaded. Ready for live plate detection.")
        except Exception as e:
            print(f"[ANPR] EasyOCR load failed: {e}")
            _reader = None
        _reader_loading = False
    return _reader


class ANPRDetector:
    """
    Detects and reads Indian vehicle number plates from OpenCV frames.
    Uses YOLO vehicle bounding boxes to focus the search region.
    """

    SCAN_INTERVAL_FRAMES = 30

    def __init__(self):
        self._frame_count = 0
        self._last_plates = []
        # Start loading EasyOCR eagerly in background
        threading.Thread(target=_get_reader, daemon=True, name="EasyOCRLoader").start()

    @property
    def is_ready(self):
        return _reader is not None

    def process_frame(self, frame, vehicle_boxes):
        """
        Called each frame from the video processor capture loop.
        vehicle_boxes: list of {"bbox": [x1,y1,x2,y2], "class": "car", ...}
        Returns: list of detected plate dicts.
        """
        self._frame_count += 1
        if self._frame_count % self.SCAN_INTERVAL_FRAMES != 0:
            return self._last_plates

        reader = _get_reader()
        if reader is None:
            return []

        if vehicle_boxes:
            plates = self._scan_vehicle_crops(frame, vehicle_boxes, reader)
        else:
            plates = self._scan_full_frame(frame, reader)

        if plates:
            self._last_plates = plates
        return self._last_plates

    def scan_frame_now(self, frame):
        """Force an immediate ANPR scan (used by API endpoint)."""
        reader = _get_reader()
        if reader is None:
            return []
        return self._scan_full_frame(frame, reader)

    def _scan_vehicle_crops(self, frame, vehicle_boxes, reader):
        results = []
        h_frame, w_frame = frame.shape[:2]

        for vbox in vehicle_boxes:
            x1, y1, x2, y2 = vbox["bbox"]
            # Plates are in the lower 35% of the vehicle bounding box
            plate_y1 = max(0, int(y1 + (y2 - y1) * 0.60))
            plate_y2 = min(h_frame, y2)
            plate_x1 = max(0, x1)
            plate_x2 = min(w_frame, x2)

            if (plate_y2 - plate_y1) < 8 or (plate_x2 - plate_x1) < 20:
                continue

            crop = frame[plate_y1:plate_y2, plate_x1:plate_x2]
            candidates = self._preprocess_and_find_plates(crop)

            for candidate_crop, _ in candidates:
                for plate_text, conf in self._ocr_crop(candidate_crop, reader):
                    results.append({
                        "plate": plate_text,
                        "confidence": conf,
                        "vehicle_class": vbox.get("class", "vehicle"),
                        "frame_bbox": [x1, y1, x2, y2],
                        "source": "vehicle_crop",
                        "timestamp": time.strftime("%H:%M:%S"),
                    })
        return results

    def _scan_full_frame(self, frame, reader):
        results = []
        for candidate_crop, bbox in self._preprocess_and_find_plates(frame):
            for plate_text, conf in self._ocr_crop(candidate_crop, reader):
                results.append({
                    "plate": plate_text,
                    "confidence": conf,
                    "vehicle_class": "unknown",
                    "frame_bbox": list(bbox),
                    "source": "full_frame",
                    "timestamp": time.strftime("%H:%M:%S"),
                })
        return results

    def _preprocess_and_find_plates(self, region):
        if region is None or region.size == 0:
            return []

        h, w = region.shape[:2]
        if w < 200:
            scale = 200 / w
            region = cv2.resize(region, (int(w * scale), int(h * scale)),
                                interpolation=cv2.INTER_CUBIC)
            h, w = region.shape[:2]

        blurred = cv2.bilateralFilter(region, 11, 17, 17)
        gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 30, 200)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

        cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:15]

        candidates = []
        for cnt in cnts:
            if cv2.contourArea(cnt) < 300:
                continue
            rx, ry, rw, rh = cv2.boundingRect(cnt)
            aspect = rw / float(rh) if rh > 0 else 0
            if 2.5 <= aspect <= 9.0 and rw > 40 and rh > 8:
                pad_x = int(rw * 0.05)
                pad_y = int(rh * 0.10)
                rx0 = max(0, rx - pad_x)
                ry0 = max(0, ry - pad_y)
                rx1 = min(w, rx + rw + pad_x)
                ry1 = min(h, ry + rh + pad_y)
                crop = region[ry0:ry1, rx0:rx1]
                if crop.size > 0:
                    candidates.append((crop, (rx0, ry0, rx1, ry1)))

        if not candidates:
            candidates = [(region, (0, 0, w, h))]

        return candidates

    def _ocr_crop(self, crop, reader):
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        results = []
        try:
            ocr_out = reader.readtext(
                thresh, detail=1, paragraph=False,
                allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "
            )
            for (_, text, prob) in ocr_out:
                normalized = self._normalize_plate(text)
                if normalized and prob >= 0.25:
                    results.append((normalized, round(prob * 100, 1)))
        except Exception:
            pass
        return results

    @staticmethod
    def _normalize_plate(raw):
        cleaned = re.sub(r"[^A-Z0-9]", "", raw.upper().strip())
        m = PLATE_REGEX.search(cleaned)
        if m:
            state, dist, series, num = m.groups()
            return f"{state} {dist.zfill(2)} {series} {num}"
        return None

    @staticmethod
    def draw_plates_on_frame(frame, plates_info):
        """Draw detected plate text overlays on a video frame."""
        for info in plates_info:
            x1, y1, x2, y2 = info.get("frame_bbox", [0, 0, 0, 0])
            plate_text = info.get("plate", "")
            conf = info.get("confidence", 0)
            if not plate_text:
                continue

            label = f"[{plate_text}] {conf:.0f}%"
            font = cv2.FONT_HERSHEY_SIMPLEX
            (tw, th), bl = cv2.getTextSize(label, font, 0.48, 1)

            lx, ly = x1, y2 + 4
            cv2.rectangle(frame, (lx, ly), (lx + tw + 6, ly + th + bl + 4),
                          (0, 200, 80), cv2.FILLED)
            cv2.putText(frame, label, (lx + 3, ly + th + 2),
                        font, 0.48, (0, 0, 0), 1, cv2.LINE_AA)
        return frame
