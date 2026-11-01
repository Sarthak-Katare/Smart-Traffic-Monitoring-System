"""
tracker.py — Phase 4: Vehicle Tracking & Unique Counting Engine

Implements an efficient Euclidean Distance Centroid Object Tracker.
Maintains persistent IDs across consecutive frames for moving vehicles,
preventing double-counting and enabling cumulative vehicle statistics.
"""

import math
import numpy as np


class CentroidTracker:
    """
    Euclidean Distance Centroid Tracker.

    Tracks object bounding box centroids across frames to maintain stable vehicle IDs.
    """

    def __init__(self, max_disappeared=15, max_distance=60):
        """
        Args:
            max_disappeared (int): Max consecutive frames an object can be missing before ID is deregistered.
            max_distance (int): Max pixel distance allowed between centroids across frames to match same ID.
        """
        self.next_object_id = 1
        self.objects = {}         # id -> {'centroid': (x, y), 'bbox': [x1,y1,x2,y2], 'class': str, 'conf': float}
        self.disappeared = {}     # id -> count of consecutive missed frames
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance
        self.total_unique_counted = 0 # Lifetime total unique vehicles seen

    def register(self, centroid, bbox, class_name, conf):
        """Register a new vehicle with a fresh unique ID."""
        self.objects[self.next_object_id] = {
            'centroid': centroid,
            'bbox': bbox,
            'class': class_name,
            'conf': conf
        }
        self.disappeared[self.next_object_id] = 0
        self.next_object_id += 1
        self.total_unique_counted += 1

    def deregister(self, object_id):
        """Remove a vehicle ID when it exits the frame/view."""
        if object_id in self.objects:
            del self.objects[object_id]
        if object_id in self.disappeared:
            del self.disappeared[object_id]

    def update(self, detections):
        """
        Update tracker with new bounding box detections for the current frame.

        Args:
            detections (list of dicts): [{'class': 'car', 'confidence': 0.9, 'bbox': [x1,y1,x2,y2]}, ...]

        Returns:
            tracked_objects (list of dicts):
                [{'id': 1, 'class': 'car', 'bbox': [...], 'centroid': (cx,cy)}, ...]
        """
        if len(detections) == 0:
            # Mark all active objects as disappeared
            for object_id in list(self.disappeared.keys()):
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)
            return self._format_output()

        # Compute centroids for incoming detections
        input_centroids = []
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            cx = int((x1 + x2) / 2.0)
            cy = int((y1 + y2) / 2.0)
            input_centroids.append((cx, cy))

        # If no objects are currently tracked, register all input detections
        if len(self.objects) == 0:
            for i, det in enumerate(detections):
                self.register(input_centroids[i], det['bbox'], det['class'], det['confidence'])
        else:
            # Grab existing object IDs and centroids
            object_ids = list(self.objects.keys())
            object_centroids = [self.objects[oid]['centroid'] for oid in object_ids]

            # Compute Euclidean distance matrix between existing centroids and input centroids
            D = np.zeros((len(object_centroids), len(input_centroids)), dtype="float")
            for i, (ox, oy) in enumerate(object_centroids):
                for j, (cx, cy) in enumerate(input_centroids):
                    D[i, j] = math.hypot(ox - cx, oy - cy)

            # Find smallest distance matches
            rows = D.min(axis=1).argsort()
            cols = D.argmin(axis=1)[rows]

            used_rows = set()
            used_cols = set()

            for (row, col) in zip(rows, cols):
                if row in used_rows or col in used_cols:
                    continue

                if D[row, col] > self.max_distance:
                    continue

                object_id = object_ids[row]
                self.objects[object_id] = {
                    'centroid': input_centroids[col],
                    'bbox': detections[col]['bbox'],
                    'class': detections[col]['class'],
                    'conf': detections[col]['confidence']
                }
                self.disappeared[object_id] = 0

                used_rows.add(row)
                used_cols.add(col)

            # Check unassigned rows (existing objects not matched)
            unused_rows = set(range(0, D.shape[0])).difference(used_rows)
            for row in unused_rows:
                object_id = object_ids[row]
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)

            # Check unassigned cols (new detected vehicles)
            unused_cols = set(range(0, D.shape[1])).difference(used_cols)
            for col in unused_cols:
                self.register(input_centroids[col], detections[col]['bbox'], detections[col]['class'], detections[col]['confidence'])

        return self._format_output()

    def _format_output(self):
        """Formats internal objects dictionary into clean API response list."""
        output = []
        for oid, data in self.objects.items():
            output.append({
                'id': oid,
                'class': data['class'],
                'confidence': data['conf'],
                'bbox': data['bbox'],
                'centroid': data['centroid']
            })
        return output
