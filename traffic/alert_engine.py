"""
alert_engine.py — Real-Time Alert System

Provides:
  - Blacklist check on every detected plate
  - Alert firing to database on blacklist hit or anomaly
  - In-memory recent alerts cache for fast dashboard polling
  - Rate limiting (prevents duplicate alerts within 5 minutes for same plate)
"""

import datetime
import threading


class AlertEngine:
    """
    Real-time alert management system.
    Wraps DatabaseManager for alert CRUD with rate-limiting and in-memory cache.
    """

    # Rate-limit: don't re-fire alert for same plate+camera within N seconds
    ALERT_COOLDOWN_SEC = 300  # 5 minutes

    def __init__(self, db_manager):
        self.db = db_manager
        self._lock = threading.Lock()
        # { "plate:camera_id" : last_alert_datetime }
        self._last_alert_time = {}

        # Seed demo blacklist on first startup
        self.db.seed_blacklist_if_empty()

    # ------------------------------------------------------------------
    # Core Alert Check — Called on every ANPR detection
    # ------------------------------------------------------------------

    def check_and_fire(self, plate, camera_id):
        """
        Checks if a detected plate warrants an alert.
        Called automatically every time an ANPR plate is confirmed.

        Returns:
            dict or None — the fired alert dict, or None if no alert.
        """
        if not plate or not camera_id:
            return None

        # Rate-limit: skip if same plate was just alerted recently
        rate_key = f"{plate}:{camera_id}"
        with self._lock:
            last = self._last_alert_time.get(rate_key)
            now = datetime.datetime.now()
            if last and (now - last).total_seconds() < self.ALERT_COOLDOWN_SEC:
                return None

        # 1. Blacklist check — CRITICAL severity
        if self.db.is_blacklisted(plate):
            bl = self._get_blacklist_entry(plate)
            reason = bl.get('reason', 'Blacklisted Vehicle') if bl else 'Blacklisted Vehicle'
            msg = f"BLACKLISTED VEHICLE DETECTED at {camera_id} Camera. Plate: {plate}. Reason: {reason}"
            alert_id = self.db.create_alert(
                plate=plate,
                alert_type='BLACKLIST_HIT',
                camera_id=camera_id,
                severity='CRITICAL',
                message=msg,
            )
            print(f"[ALERT] *** CRITICAL *** {msg}")
            with self._lock:
                self._last_alert_time[rate_key] = datetime.datetime.now()
            return {
                'id': alert_id, 'plate': plate, 'alert_type': 'BLACKLIST_HIT',
                'severity': 'CRITICAL', 'message': msg, 'camera_id': camera_id,
            }

        # 2. Anomaly: same plate at 3+ different cameras in last 10 minutes
        anomaly = self._check_rapid_movement(plate)
        if anomaly:
            msg = f"RAPID MOVEMENT ANOMALY: Plate {plate} detected at {anomaly} camera nodes in under 10 minutes."
            alert_id = self.db.create_alert(
                plate=plate,
                alert_type='RAPID_MOVEMENT_ANOMALY',
                camera_id=camera_id,
                severity='WARNING',
                message=msg,
            )
            print(f"[ALERT] WARNING: {msg}")
            with self._lock:
                self._last_alert_time[rate_key] = datetime.datetime.now()
            return {
                'id': alert_id, 'plate': plate, 'alert_type': 'RAPID_MOVEMENT_ANOMALY',
                'severity': 'WARNING', 'message': msg, 'camera_id': camera_id,
            }

        return None

    def _check_rapid_movement(self, plate):
        """Returns count of distinct cameras in last 10 min if suspicious, else None."""
        try:
            events = self.db.get_plate_trajectory(plate)
            if not events:
                return None
            cutoff = datetime.datetime.now() - datetime.timedelta(minutes=10)
            recent = [
                e for e in events
                if datetime.datetime.strptime(e['timestamp'], '%Y-%m-%d %H:%M:%S') >= cutoff
            ]
            distinct_cams = len(set(e['camera_id'] for e in recent))
            return distinct_cams if distinct_cams >= 3 else None
        except Exception:
            return None

    def _get_blacklist_entry(self, plate):
        """Returns the blacklist entry dict for a plate, or None."""
        clean = plate.upper().replace(' ', '').replace('-', '')
        entries = self.db.get_blacklist()
        for e in entries:
            if e['plate'] == clean:
                return e
        return None

    # ------------------------------------------------------------------
    # Blacklist Management API
    # ------------------------------------------------------------------

    def add_to_blacklist(self, plate, reason='Flagged by Operator', flagged_by='User'):
        return self.db.add_to_blacklist(plate, reason, flagged_by)

    def remove_from_blacklist(self, plate):
        return self.db.remove_from_blacklist(plate)

    def get_blacklist(self):
        return self.db.get_blacklist()

    def is_blacklisted(self, plate):
        return self.db.is_blacklisted(plate)

    # ------------------------------------------------------------------
    # Alert Retrieval & Management
    # ------------------------------------------------------------------

    def get_active_alerts(self, limit=30):
        return self.db.get_active_alerts(limit=limit)

    def get_all_alerts(self, limit=100):
        return self.db.get_all_alerts(limit=limit)

    def resolve_alert(self, alert_id):
        return self.db.resolve_alert(alert_id)

    def get_alert_summary(self):
        return self.db.get_alert_summary()
