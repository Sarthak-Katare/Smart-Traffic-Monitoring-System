"""
density_engine.py — Phase 5: Traffic Density Analysis Engine

Calculates PCU (Passenger Car Unit) weighted traffic density per lane:
  - Car = 1.0 PCU
  - Motorcycle = 0.5 PCU
  - Bus = 2.5 PCU
  - Truck = 3.0 PCU

Categorizes lane congestion into 4 density levels:
  - LOW (0-3.0 PCU)
  - MEDIUM (3.1-7.0 PCU)
  - HIGH (7.1-12.0 PCU)
  - CRITICAL (>12.0 PCU)
"""

import config


class DensityEngine:
    """Calculates weighted traffic density and density levels for each intersection lane."""

    # PCU Weight factors per vehicle type
    PCU_WEIGHTS = {
        'car':        1.0,
        'motorcycle': 0.5,
        'bus':        2.5,
        'truck':      3.0
    }

    @classmethod
    def calculate_lane_density(cls, lane_vehicles):
        """
        Calculate traffic metrics for a single lane's vehicle list.

        Args:
            lane_vehicles (list of dicts): vehicles tracked in this lane

        Returns:
            dict: {
               'raw_count': int,
               'pcu_score': float,
               'density_level': 'LOW'|'MEDIUM'|'HIGH'|'CRITICAL',
               'breakdown': {'cars': 0, 'motorcycles': 0, 'buses': 0, 'trucks': 0}
            }
        """
        breakdown = {'cars': 0, 'motorcycles': 0, 'buses': 0, 'trucks': 0}
        pcu_score = 0.0

        for v in lane_vehicles:
            cls_name = v['class']
            if cls_name == 'car':
                breakdown['cars'] += 1
                pcu_score += cls.PCU_WEIGHTS['car']
            elif cls_name == 'motorcycle':
                breakdown['motorcycles'] += 1
                pcu_score += cls.PCU_WEIGHTS['motorcycle']
            elif cls_name == 'bus':
                breakdown['buses'] += 1
                pcu_score += cls.PCU_WEIGHTS['bus']
            elif cls_name == 'truck':
                breakdown['trucks'] += 1
                pcu_score += cls.PCU_WEIGHTS['truck']

        # Determine density level threshold
        if pcu_score <= 3.0:
            level = 'LOW'
        elif pcu_score <= 7.0:
            level = 'MEDIUM'
        elif pcu_score <= 12.0:
            level = 'HIGH'
        else:
            level = 'CRITICAL'

        return {
            'raw_count': len(lane_vehicles),
            'pcu_score': round(pcu_score, 1),
            'density_level': level,
            'breakdown': breakdown
        }

    @classmethod
    def analyze_all_lanes(cls, lane_classified_vehicles):
        """
        Analyzes all 4 lanes (North, South, East, West).

        Args:
            lane_classified_vehicles (dict): output from LaneManager.classify_vehicles_by_lane

        Returns:
            dict: {
               'North': {...},
               'South': {...},
               'East':  {...},
               'West':  {...}
            }
        """
        results = {}
        for lane_name in ('North', 'South', 'East', 'West'):
            vehicles_in_lane = lane_classified_vehicles.get(lane_name, [])
            results[lane_name] = cls.calculate_lane_density(vehicles_in_lane)

        return results
