"""
lane_manager.py — Phase 5: Multi-Lane ROI Region Manager

Defines 4 intersection lane regions (North, South, East, West) within the 640x360 frame.
Renders clean ROI polygon boundaries on the video stream and maps vehicle centroids
to their respective lane regions.
"""

import cv2
import numpy as np


class LaneManager:
    """
    Manages 4 intersection lane ROI regions:
      - North: Top-Left quadrant (0..320, 0..180)
      - South: Bottom-Left quadrant (0..320, 180..360)
      - East:  Top-Right quadrant (320..640, 0..180)
      - West:  Bottom-Right quadrant (320..640, 180..360)
    """

    def __init__(self, frame_width=640, frame_height=360):
        self.width = frame_width
        self.height = frame_height
        self.mid_x = frame_width // 2
        self.mid_y = frame_height // 2

        # Color definitions (BGR) for semi-transparent ROI borders & labels
        self.LANE_COLORS = {
            'North': (255, 180,   0),   # Cyan/Blue
            'South': ( 50, 200, 255),   # Amber/Orange
            'East':  (100, 220,  50),   # Emerald/Green
            'West':  (200,  80, 255)    # Purple/Pink
        }

    def assign_lane(self, centroid):
        """
        Map vehicle centroid (cx, cy) to a lane region name.

        Returns:
            str: 'North', 'South', 'East', or 'West'
        """
        cx, cy = centroid

        if cx < self.mid_x and cy < self.mid_y:
            return 'North'
        elif cx < self.mid_x and cy >= self.mid_y:
            return 'South'
        elif cx >= self.mid_x and cy < self.mid_y:
            return 'East'
        else:
            return 'West'

    def classify_vehicles_by_lane(self, tracked_vehicles):
        """
        Group tracked vehicles into per-lane dictionaries.

        Args:
            tracked_vehicles (list of dicts): output from CentroidTracker

        Returns:
            dict: {
               'North': [{'id':1, 'class':'car', ...}, ...],
               'South': [...],
               'East':  [...],
               'West':  [...]
            }
        """
        lane_data = {
            'North': [],
            'South': [],
            'East':  [],
            'West':  []
        }

        for vehicle in tracked_vehicles:
            lane = self.assign_lane(vehicle['centroid'])
            lane_data[lane].append(vehicle)

        return lane_data

    def draw_lane_overlays(self, frame):
        """
        Draw clean semi-transparent grid lines and ROI labels for North, South, East, West.
        """
        overlay = frame.copy()

        # Center dividing lines (dashed effect or thin line)
        cv2.line(overlay, (self.mid_x, 0), (self.mid_x, self.height), (120, 120, 120), 1, cv2.LINE_AA)
        cv2.line(overlay, (0, self.mid_y), (self.width, self.mid_y), (120, 120, 120), 1, cv2.LINE_AA)

        # Draw Lane Labels in each quadrant corners
        labels = [
            ('NORTH LANE', (15, self.mid_y - 12), self.LANE_COLORS['North']),
            ('SOUTH LANE', (15, self.height - 12), self.LANE_COLORS['South']),
            ('EAST LANE',  (self.mid_x + 15, self.mid_y - 12), self.LANE_COLORS['East']),
            ('WEST LANE',  (self.mid_x + 15, self.height - 12), self.LANE_COLORS['West']),
        ]

        for text, pos, color in labels:
            cv2.putText(
                overlay, text, pos,
                cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                color, 1, cv2.LINE_AA
            )

        # Blend overlay with original frame (alpha = 0.85)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
        return frame
