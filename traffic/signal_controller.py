"""
signal_controller.py — Phase 6, 7 & 8: Dynamic Traffic Signal Optimization & Emergency Override Engine

Responsibilities:
  - Manages 4-way intersection traffic signal state machine (North, South, East, West)
  - Calculates dynamic green light duration based on AI lane density (PCU score)
  - Priority Preemption: Automatically selects the lane with highest traffic density for the next green phase
  - Emergency Manual Override Mode: Forces GREEN on any designated lane (e.g. Ambulances, Fire Trucks)
  - Handles Green -> Yellow (3s) -> Red transitions smoothly
  - Thread-safe background timer updates countdown every second
"""

import time
import threading
import config


class SignalController:
    """
    Dynamic Traffic Signal Optimization Controller with Emergency Override.

    Cycle (AI Mode):
      GREEN (15s-60s based on AI density) -> YELLOW (3s) -> RED -> (Next Priority Lane GREEN)

    Override Mode:
      Forces specified lane GREEN immediately until released or timer expires.
    """

    LANES = ['North', 'East', 'South', 'West']

    def __init__(self):
        self.active_lane_index = 0             # Default starting green lane: 'North'
        self.active_state = 'GREEN'            # 'GREEN', 'YELLOW', or 'RED'
        self.remaining_seconds = config.BASE_GREEN_TIME
        self.current_allocated_green = config.BASE_GREEN_TIME

        # Manual Emergency Override State
        self.is_override_active = False
        self.override_lane_name = None
        self.override_seconds = 0

        self.lock = threading.Lock()
        self.is_running = False
        self.thread = None

        # Per-lane status dictionary returned to UI
        self.lane_analytics_cache = {}

    def calculate_green_time(self, pcu_score, vehicle_count):
        """
        Dynamic Green Time Algorithm:
          Green = BASE_GREEN_TIME + (PCU_Score * SEC_PER_VEHICLE)
          Clamped between MIN_GREEN_TIME and MAX_GREEN_TIME.
        """
        extra_seconds = int(pcu_score * config.SEC_PER_VEHICLE)
        allocated = config.BASE_GREEN_TIME + extra_seconds
        return max(config.MIN_GREEN_TIME, min(config.MAX_GREEN_TIME, allocated))

    def select_next_lane(self, lane_analytics):
        """
        Adaptive AI Priority Selection:
        Selects the lane with the highest PCU traffic density for the next GREEN phase.
        If all lanes are equal/low density, falls back to round-robin order.
        """
        highest_lane = None
        highest_pcu = -1.0

        for lane_name in self.LANES:
            info = lane_analytics.get(lane_name, {'pcu_score': 0.0})
            score = info.get('pcu_score', 0.0)
            if score > highest_pcu:
                highest_pcu = score
                highest_lane = lane_name

        if highest_pcu <= 0 or highest_lane is None:
            next_idx = (self.active_lane_index + 1) % len(self.LANES)
            return self.LANES[next_idx]

        return highest_lane

    def set_manual_override(self, lane_name, duration=30):
        """
        Activates Emergency Manual Override to force GREEN light on designated lane.
        """
        if lane_name not in self.LANES:
            return False, f"Invalid lane name: {lane_name}"

        with self.lock:
            self.is_override_active = True
            self.override_lane_name = lane_name
            self.active_lane_index = self.LANES.index(lane_name)
            self.active_state = 'GREEN'
            self.remaining_seconds = duration
            self.current_allocated_green = duration

        print(f"[EMERGENCY OVERRIDE] Manual override engaged -> Forced GREEN on {lane_name} for {duration}s")
        return True, f"Emergency override activated on {lane_name} Lane for {duration} seconds."

    def release_manual_override(self):
        """
        Releases emergency override and returns intersection to AI Dynamic Mode.
        """
        with self.lock:
            self.is_override_active = False
            self.override_lane_name = None
            self.remaining_seconds = config.BASE_GREEN_TIME
            self.current_allocated_green = config.BASE_GREEN_TIME

        print("[EMERGENCY OVERRIDE] Manual override released -> Resumed AI Dynamic Timing")
        return True, "Emergency override released. AI Dynamic Control resumed."

    def update_lane_data(self, lane_analytics):
        """Called by background detection thread whenever frame density is updated."""
        with self.lock:
            self.lane_analytics_cache = lane_analytics

    def start(self):
        """Start the signal controller background timer thread."""
        if self.is_running:
            return

        self.is_running = True
        self.thread = threading.Thread(target=self._timer_loop, daemon=True)
        self.thread.start()
        print("[SIGNAL CONTROLLER] Started dynamic 4-way signal timing engine.")

    def stop(self):
        """Stop background timer."""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        print("[SIGNAL CONTROLLER] Stopped.")

    def _timer_loop(self):
        """Main 1-second interval state machine loop."""
        while self.is_running:
            time.sleep(1.0)

            with self.lock:
                # If Manual Emergency Override is active, process override countdown
                if self.is_override_active:
                    self.remaining_seconds -= 1
                    if self.remaining_seconds <= 0:
                        # Auto-release override when timer expires
                        self.is_override_active = False
                        self.override_lane_name = None
                        self.remaining_seconds = config.BASE_GREEN_TIME
                        print("[EMERGENCY OVERRIDE] Override timer expired -> Resuming AI Dynamic Control")
                    continue

                # --- Standard AI Dynamic Timing Cycle ---
                self.remaining_seconds -= 1

                # Transition to YELLOW 3 seconds before green expires
                if self.remaining_seconds == 3 and self.active_state == 'GREEN':
                    self.active_state = 'YELLOW'

                # Green/Yellow phase expired -> Switch to next priority lane
                elif self.remaining_seconds <= 0:
                    current_lane = self.LANES[self.active_lane_index]
                    next_lane = self.select_next_lane(self.lane_analytics_cache)

                    lane_info = self.lane_analytics_cache.get(next_lane, {'pcu_score': 0.0, 'raw_count': 0})
                    new_green_time = self.calculate_green_time(
                        lane_info.get('pcu_score', 0.0),
                        lane_info.get('raw_count', 0)
                    )

                    self.active_lane_index = self.LANES.index(next_lane)
                    self.active_state = 'GREEN'
                    self.current_allocated_green = new_green_time
                    self.remaining_seconds = new_green_time

                    print(f"[SIGNAL CONTROLLER] Phase Change -> Active Green Lane: {next_lane} ({new_green_time}s)")

    def get_ordered_waiting_lanes(self, active_lane, lane_analytics):
        """
        Orders the waiting RED lanes by AI traffic priority (highest PCU score first).
        If tied or zero, falls back to round-robin clockwise sequence.
        """
        waiting = [l for l in self.LANES if l != active_lane]
        
        # Sort by PCU score descending, keeping stable order
        def priority_key(lane_name):
            info = lane_analytics.get(lane_name, {})
            pcu = info.get('pcu_score', 0.0)
            count = info.get('raw_count', 0)
            return (pcu, count)

        # If any lane has traffic, sort by traffic density
        has_traffic = any(lane_analytics.get(l, {}).get('pcu_score', 0.0) > 0 for l in waiting)
        if has_traffic:
            return sorted(waiting, key=priority_key, reverse=True)
        else:
            # Clockwise cyclic order relative to active lane
            idx = self.LANES.index(active_lane)
            return [self.LANES[(idx + 1 + i) % len(self.LANES)] for i in range(len(waiting))]

    def calculate_wait_times(self, active_lane, remaining_active_sec, lane_analytics):
        """
        Calculates exact dynamic waiting time for every lane in the intersection.

        - Active Green Lane: wait_time = 0s
        - 1st Waiting Lane: wait_time = remaining_active_sec
        - 2nd Waiting Lane: wait_time = remaining_active_sec + Green(1st) + Yellow(3s)
        - 3rd Waiting Lane: wait_time = remaining_active_sec + Green(1st) + Yellow(3s) + Green(2nd) + Yellow(3s)
        """
        wait_times = {}
        queue_positions = {}
        yellow_time = config.YELLOW_LIGHT_TIME

        # Active lane has zero wait time
        wait_times[active_lane] = 0
        queue_positions[active_lane] = 0

        ordered_waiting = self.get_ordered_waiting_lanes(active_lane, lane_analytics)

        accumulated_wait = remaining_active_sec

        for i, lane in enumerate(ordered_waiting, 1):
            queue_positions[lane] = i
            wait_times[lane] = accumulated_wait

            # Calculate green time allocated for this waiting lane
            lane_info = lane_analytics.get(lane, {'pcu_score': 0.0, 'raw_count': 0})
            lane_green = self.calculate_green_time(
                lane_info.get('pcu_score', 0.0),
                lane_info.get('raw_count', 0)
            )

            # Add to accumulator for the next waiting lane
            accumulated_wait += lane_green + yellow_time

        return wait_times, queue_positions

    def get_signal_state(self):
        """
        Returns full state dictionary for /api/stats, logging, and dashboard updates
        including real-time dynamic wait times for every lane.
        """
        with self.lock:
            active_lane_name = self.LANES[self.active_lane_index]
            lanes_response = {}

            # Calculate dynamic wait times for all lanes
            wait_times, queue_positions = self.calculate_wait_times(
                active_lane_name,
                max(0, self.remaining_seconds),
                self.lane_analytics_cache
            )

            for lane in self.LANES:
                info = self.lane_analytics_cache.get(lane, {
                    'raw_count': 0, 'pcu_score': 0.0, 'density_level': 'LOW', 'breakdown': {}
                })

                rec_green = self.calculate_green_time(
                    info.get('pcu_score', 0.0),
                    info.get('raw_count', 0)
                )

                if lane == active_lane_name:
                    status = self.active_state  # 'GREEN' or 'YELLOW'
                else:
                    status = 'RED'

                wait_sec = wait_times.get(lane, 0)
                pos = queue_positions.get(lane, 0)
                pcu = info.get('pcu_score', 0.0)
                clearance_est = round(pcu * config.AVG_CLEARANCE_RATE, 1)

                lanes_response[lane] = {
                    'count': info.get('raw_count', 0),
                    'pcu_score': pcu,
                    'density': info.get('density_level', 'LOW'),
                    'green_time': rec_green,
                    'status': status,
                    'wait_time': wait_sec,
                    'queue_position': pos,
                    'clearance_estimate': clearance_est,
                    'breakdown': info.get('breakdown', {})
                }

            return {
                'active_green_lane': active_lane_name,
                'active_state': self.active_state,
                'remaining_seconds': max(0, self.remaining_seconds),
                'allocated_green': self.current_allocated_green,
                'override_active': self.is_override_active,
                'override_lane': self.override_lane_name,
                'lanes': lanes_response
            }

