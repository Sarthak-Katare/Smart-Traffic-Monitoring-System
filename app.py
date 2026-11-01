"""
app.py — City-Wide ANPR Intelligence Platform
Flask Web Application Server — 4-Lane Multi-Video, Trajectory Tracking, Analytics & Alert System
"""

import os
import time
import datetime
import threading
from flask import Flask, render_template, jsonify, Response, request
from werkzeug.utils import secure_filename

import config
from detection.multi_video_processor import MultiLaneVideoProcessor
from detection.detector import VehicleDetector
from traffic.signal_controller import SignalController
from traffic.vahan_service import VahanVerificationService
from database.db_manager import DatabaseManager
from traffic.trajectory_engine import TrajectoryEngine
from traffic.alert_engine import AlertEngine
from traffic.analytics_engine import AnalyticsEngine
from utils.video_splitter import ensure_lane_videos

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB max upload limit

# Ensure default 4 lane videos exist in videos/
ensure_lane_videos()

# Global Core Instances
vehicle_detector = VehicleDetector()
signal_controller = SignalController()
db_manager = DatabaseManager()
trajectory_engine = TrajectoryEngine(db_manager)
alert_engine = AlertEngine(db_manager)
analytics_engine = AnalyticsEngine(db_manager)
multi_video_processor = MultiLaneVideoProcessor(
    detector=vehicle_detector,
    trajectory_engine=trajectory_engine,
    alert_engine=alert_engine,
)

# Load YOLO Model at Startup
_model_loaded, _model_msg = vehicle_detector.load_model()
print(f"[YOLO] {_model_msg}")

# Start Dynamic Signal Optimization & Wait Time Engine
signal_controller.start()

# Auto-start video streams on startup so cameras are live immediately
multi_video_processor.start()
print("[CITY AI] TrajectoryEngine, AlertEngine, AnalyticsEngine initialized.")


# --- Background Database Logging Engine (Logs snapshot every 10 seconds) ---
def _auto_log_loop():
    while True:
        time.sleep(10)
        try:
            total = multi_video_processor.get_total_vehicles()
            breakdown = multi_video_processor.get_breakdown()
            lane_analytics = multi_video_processor.get_lane_analytics_all()

            signal_controller.update_lane_data(lane_analytics)
            sig_state = signal_controller.get_signal_state()

            snapshot_data = {
                'total_vehicles': total,
                'breakdown': breakdown,
                'lanes': sig_state['lanes'],
                'active_green_lane': sig_state['active_green_lane']
            }
            db_manager.log_snapshot(snapshot_data)
        except Exception as e:
            print(f"[AUTO-LOGGER] Logging error: {e}")

threading.Thread(target=_auto_log_loop, daemon=True).start()
print("[DATABASE] Background 10-second traffic logger started.")


# ==========================================================================
# Web Page Routes
# ==========================================================================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/history')
def history():
    return render_template('history.html')


@app.route('/trajectory')
def trajectory_page():
    return render_template('trajectory.html')


@app.route('/analytics')
def analytics_page():
    return render_template('analytics.html')


@app.route('/alerts')
def alerts_page():
    return render_template('alerts.html')


# ==========================================================================
# 4-Lane Video Streaming Routes
# ==========================================================================

@app.route('/video_feed')
@app.route('/video_feed/combined')
def video_feed_combined():
    """Returns 2x2 Composite Quad-View MJPEG stream (North, East, South, West)."""
    if not multi_video_processor.is_running:
        return Response(status=204)

    return Response(
        multi_video_processor.generate_composite_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/video_feed/<lane_name>')
def video_feed_lane(lane_name):
    """Returns individual MJPEG stream for a specific lane (North, East, South, West)."""
    lane_name_clean = lane_name.capitalize()
    if lane_name_clean not in config.LANE_NAMES:
        return Response("Invalid lane name. Use North, East, South, or West.", status=400)

    if not multi_video_processor.is_running:
        return Response(status=204)

    return Response(
        multi_video_processor.generate_lane_frames(lane_name_clean),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/api/video/start', methods=['POST'])
def start_video():
    """Starts or restarts the 4-lane video processing engine."""
    success, message = multi_video_processor.start()
    return jsonify({
        'success': success,
        'message': message,
        'yolo_active': vehicle_detector.is_loaded,
        'status': multi_video_processor.get_status()
    }), (200 if success else 500)


@app.route('/api/video/stop', methods=['POST'])
def stop_video():
    """Stops all 4 lane video capture feeds."""
    multi_video_processor.stop()
    return jsonify({'success': True, 'message': 'All 4 video feeds stopped.'}), 200


@app.route('/api/video/status', methods=['GET'])
def video_status():
    """Returns current status of all 4 video feeds."""
    return jsonify(multi_video_processor.get_status()), 200


@app.route('/api/video/list_files', methods=['GET'])
def list_video_files():
    """Returns available video files in videos/ and videos/uploads/."""
    files = []
    allowed_exts = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}

    # Root videos dir
    if os.path.exists(config.VIDEO_DIR):
        for f in os.listdir(config.VIDEO_DIR):
            p = os.path.join(config.VIDEO_DIR, f)
            if os.path.isfile(p) and os.path.splitext(f)[1].lower() in allowed_exts:
                files.append({'name': f, 'path': p, 'folder': 'default'})

    # Uploads dir
    if os.path.exists(config.UPLOAD_DIR):
        for f in os.listdir(config.UPLOAD_DIR):
            p = os.path.join(config.UPLOAD_DIR, f)
            if os.path.isfile(p) and os.path.splitext(f)[1].lower() in allowed_exts:
                files.append({'name': f, 'path': p, 'folder': 'uploads'})

    return jsonify({'success': True, 'files': files}), 200


@app.route('/api/video/list_webcams', methods=['GET'])
def list_webcams():
    """Returns available camera index options instantly without blocking hardware probe."""
    return jsonify({
        'success': True,
        'webcams': [
            {'index': 0, 'name': 'Camera 0 (Default / Laptop Webcam)'},
            {'index': 1, 'name': 'Camera 1 (External USB Camera)'},
            {'index': 2, 'name': 'Camera 2 (Secondary USB Camera)'}
        ]
    }), 200


@app.route('/api/video/set_source', methods=['POST'])
def set_lane_video_source():
    """
    Sets the video file path, webcam, or RTSP/HTTP live stream for a specific lane.
    JSON payload:
      {"lane": "North", "source": "lane_north.mp4"}
      {"lane": "North", "source": "webcam"} or {"lane": "North", "source": 0}
      {"lane": "North", "source": "rtsp://..."}
      {"lane": "North", "source": "http://192.168.1.50:8080/video"}
    """
    data = request.get_json(silent=True) or {}
    lane = data.get('lane', 'North').capitalize()
    source = data.get('source', '')

    if lane not in config.LANE_NAMES:
        return jsonify({'success': False, 'message': f'Invalid lane: {lane}'}), 400

    target_path = None
    if source == 'webcam' or source == '0' or source == 0:
        target_path = 0
    elif isinstance(source, int):
        target_path = source
    elif isinstance(source, str) and source.strip().isdigit():
        target_path = int(source.strip())
    elif isinstance(source, str) and source.startswith(('rtsp://', 'http://', 'https://')):
        target_path = source.strip()
    elif isinstance(source, str):
        # File path
        if os.path.isabs(source) and os.path.exists(source):
            target_path = source
        else:
            cand1 = os.path.join(config.VIDEO_DIR, source)
            cand2 = os.path.join(config.UPLOAD_DIR, source)
            if os.path.exists(cand1):
                target_path = cand1
            elif os.path.exists(cand2):
                target_path = cand2
            else:
                return jsonify({'success': False, 'message': f'Video file not found: {source}'}), 404
    else:
        return jsonify({'success': False, 'message': 'Invalid video source format.'}), 400

    ok, msg = multi_video_processor.set_lane_source(lane, target_path)
    return jsonify({'success': ok, 'message': msg}), (200 if ok else 400)


@app.route('/api/video/upload/<lane_name>', methods=['POST'])
def upload_lane_video(lane_name):
    """
    Uploads a custom video file for a specific lane and sets it as that lane's active input.
    """
    lane = lane_name.capitalize()
    if lane not in config.LANE_NAMES:
        return jsonify({'success': False, 'message': f'Invalid lane name: {lane}'}), 400

    if 'video_file' not in request.files:
        return jsonify({'success': False, 'message': 'No video file provided in request.'}), 400

    file = request.files['video_file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file.'}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {'.mp4', '.avi', '.mov', '.mkv', '.webm'}:
        return jsonify({'success': False, 'message': 'Unsupported video format. Use MP4, AVI, MOV, MKV, or WEBM.'}), 400

    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    filename = secure_filename(f"lane_{lane.lower()}_{int(time.time())}{ext}")
    dest_path = os.path.join(config.UPLOAD_DIR, filename)
    file.save(dest_path)

    # Set as new source for this lane
    ok, msg = multi_video_processor.set_lane_source(lane, dest_path)

    return jsonify({
        'success': ok,
        'message': f"Uploaded and assigned {filename} to {lane} Lane.",
        'filename': filename,
        'path': dest_path
    }), 200


# ==========================================================================
# Detection & Dynamic Signal API Routes
# ==========================================================================

@app.route('/api/detections', methods=['GET'])
def get_detections():
    """Returns real-time vehicle detections across all 4 lane video feeds."""
    return jsonify({
        'timestamp': datetime.datetime.now().isoformat(),
        'active_vehicles': multi_video_processor.get_total_vehicles(),
        'lifetime_unique': multi_video_processor.get_lifetime_total(),
        'lanes': multi_video_processor.get_lane_analytics_all()
    }), 200


@app.route('/api/stats', methods=['GET'])
def current_stats():
    """
    Returns live traffic statistics from all 4 lane video streams:
    - Vehicle counts & classification breakdown
    - Per-lane PCU densities & queue delays
    - Dynamic signal states & per-lane dynamic wait times
    """
    total = multi_video_processor.get_total_vehicles()
    lifetime = multi_video_processor.get_lifetime_total()
    breakdown = multi_video_processor.get_breakdown()
    lane_analytics = multi_video_processor.get_lane_analytics_all()

    # Pass 4-lane video metrics to signal & wait time controller
    signal_controller.update_lane_data(lane_analytics)
    sig_state = signal_controller.get_signal_state()

    return jsonify({
        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_vehicles': total,
        'lifetime_vehicles': lifetime,
        'breakdown': breakdown,
        'yolo_active': vehicle_detector.is_loaded,
        'stream_active': multi_video_processor.is_running,
        'lanes': sig_state['lanes'],
        'active_green_lane': sig_state['active_green_lane'],
        'active_state': sig_state['active_state'],
        'remaining_seconds': sig_state['remaining_seconds'],
        'allocated_green': sig_state['allocated_green'],
        'override_active': sig_state['override_active'],
        'override_lane': sig_state['override_lane'],
        'video_status': multi_video_processor.get_status()
    }), 200


@app.route('/api/signal/override', methods=['POST'])
def manual_override():
    """
    Handles emergency vehicle priority & manual signal override.
    """
    data = request.get_json(silent=True) or {}
    action = data.get('action', 'enable')
    lane = data.get('lane', 'North').capitalize()
    duration = int(data.get('duration', 30))

    if action == 'disable':
        ok, msg = signal_controller.release_manual_override()
        return jsonify({'success': ok, 'message': msg}), 200
    else:
        ok, msg = signal_controller.set_manual_override(lane, duration)
        return jsonify({'success': ok, 'message': msg}), (200 if ok else 400)


# ==========================================================================
# History & Database API Routes
# ==========================================================================

@app.route('/api/history', methods=['GET'])
def get_history():
    """Fetches historical traffic analytics logs from SQLite."""
    limit = request.args.get('limit', default=50, type=int)
    logs = db_manager.get_recent_logs(limit=limit)
    summary = db_manager.get_summary_analytics()

    return jsonify({
        'success': True,
        'total_logs': len(logs),
        'summary': summary,
        'logs': logs
    }), 200


@app.route('/api/history/clear', methods=['POST'])
def clear_history():
    ok = db_manager.clear_all_logs()
    return jsonify({'success': ok, 'message': 'History logs cleared.'}), 200


# ==========================================================================
# System API Routes
# ==========================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'ok',
        'service': 'Smart Traffic Optimization AI System (4-Lane Multi-Video)',
        'timestamp': datetime.datetime.now().isoformat(),
        'active_lanes': config.LANE_NAMES
    }), 200


@app.route('/api/status', methods=['GET'])
def system_status():
    return jsonify({
        'status': 'online',
        'version': '11.0.0',
        'system_config': {
            'yolo_model': config.MODEL_NAME,
            'confidence_threshold': config.CONFIDENCE_THRESHOLD,
            'base_green_time': config.BASE_GREEN_TIME,
            'min_green_time': config.MIN_GREEN_TIME,
            'max_green_time': config.MAX_GREEN_TIME,
            'sec_per_vehicle': config.SEC_PER_VEHICLE,
            'yellow_light_time': config.YELLOW_LIGHT_TIME,
            'process_width': config.PROCESS_WIDTH,
            'process_height': config.PROCESS_HEIGHT,
            'stream_fps': config.STREAM_FPS,
            'lanes': config.LANE_NAMES
        },
        'detector': vehicle_detector.get_status(),
        'signal_controller': signal_controller.get_signal_state(),
        'video_processor': multi_video_processor.get_status()
    }), 200


# ==========================================================================
# VAHAN Vehicle RC Verification & ANPR Routes
# ==========================================================================

@app.route('/api/vahan/verify', methods=['POST'])
def vahan_verify():
    """Verify a vehicle RC by registration number against VAHAN database."""
    data = request.get_json(silent=True) or {}
    if not data or 'registration_number' not in data:
        return jsonify({'success': False, 'message': 'Missing registration_number field.'}), 400

    plate = data['registration_number'].strip()
    result = VahanVerificationService.verify_vehicle(plate)

    if not result['success']:
        return jsonify(result), 400
    return jsonify(result), 200


@app.route('/api/vahan/recent', methods=['GET'])
def vahan_recent():
    """Returns recently verified plates from the live ANPR detection log."""
    plates = multi_video_processor.get_all_detected_plates()
    return jsonify({
        'success': True,
        'count': len(plates),
        'plates': plates
    }), 200


@app.route('/api/vahan/anpr_scan', methods=['POST'])
def vahan_anpr_scan():
    """
    Performs an on-demand ANPR scan on the current live camera frame.
    Returns full VAHAN RC data for the best-detected plate.
    """
    # Prefer the lane specified in request body, else use any active lane
    body = request.get_json(silent=True) or {}
    requested_lane = body.get('lane', None)

    frame = multi_video_processor.get_best_current_frame(requested_lane)

    if frame is None:
        return jsonify({'success': False, 'message': 'No active camera frame available.'}), 503

    # Run immediate ANPR on the frame
    anpr = multi_video_processor.anpr
    plates_found = anpr.scan_frame_now(frame)

    if plates_found:
        # Pick highest-confidence result
        best = max(plates_found, key=lambda p: p.get('confidence', 0))
        plate_text = best['plate']
        vahan_result = VahanVerificationService.verify_vehicle(plate_text)
        if vahan_result['success']:
            vahan_result['anpr_raw'] = best
            vahan_result['camera_source'] = requested_lane or 'Auto'
            return jsonify(vahan_result), 200
        return jsonify({'success': False, 'message': f'Plate {plate_text} detected but VAHAN lookup failed.',
                        'detected_plate': plate_text}), 200

    # Fallback: return from already-accumulated live detections
    all_plates = multi_video_processor.get_all_detected_plates()
    if all_plates:
        best_cached = all_plates[0]
        plate_text = best_cached['plate']
        vahan_result = VahanVerificationService.verify_vehicle(plate_text)
        if vahan_result['success']:
            vahan_result['anpr_raw'] = best_cached
            vahan_result['camera_source'] = best_cached.get('lane', 'Cache')
            return jsonify(vahan_result), 200

    return jsonify({
        'success': False,
        'message': 'No plates detected in current frame. Point camera at a vehicle with a visible plate.'
    }), 200


@app.route('/api/anpr/live', methods=['GET'])
def anpr_live_log():
    """Returns the live rolling log of last 20 detected plates across all lanes."""
    plates = multi_video_processor.get_all_detected_plates()
    return jsonify({
        'success': True,
        'anpr_ready': multi_video_processor.anpr.is_ready,
        'count': len(plates),
        'plates': plates
    }), 200


# ==========================================================================
# Trajectory API Routes
# ==========================================================================

@app.route('/api/trajectory/<plate>', methods=['GET'])
def get_trajectory(plate):
    """Returns the full spatial-temporal trajectory for a given plate."""
    result = trajectory_engine.get_trajectory(plate)
    return jsonify(result), 200


@app.route('/api/trajectory/recent', methods=['GET'])
def get_recent_events():
    """Returns the recent plate sighting events feed."""
    limit = request.args.get('limit', default=50, type=int)
    events = trajectory_engine.get_recent_events(limit=limit)
    return jsonify({'success': True, 'count': len(events), 'events': events}), 200


@app.route('/api/trajectory/nodes', methods=['GET'])
def get_camera_nodes():
    """Returns camera node registry with GPS coordinates and activity levels."""
    nodes = trajectory_engine.get_camera_nodes()
    return jsonify({'success': True, 'nodes': nodes}), 200


@app.route('/api/trajectory/seed_demo', methods=['POST'])
def seed_demo_trajectories():
    """Seeds realistic demo trajectory events for all known plates (for demonstration)."""
    import random
    from traffic.trajectory_engine import CAMERA_NODES
    plates = [
        'DL 01 AB 1234', 'MH 12 DE 1433', 'KA 05 MJ 9988', 'HR 26 DQ 5501',
        'DL09XY7799',   # Blacklisted
        'UP16CD7712',   # Blacklisted
    ]
    cameras = list(CAMERA_NODES.keys())
    count = 0
    for plate in plates:
        # Create a plausible multi-camera journey
        route = random.sample(cameras, k=random.randint(2, 4))
        for cam in route:
            trajectory_engine.log_sighting(
                plate=plate, camera_id=cam,
                confidence=round(random.uniform(82.0, 99.5), 1),
                vehicle_class=random.choice(['car', 'motorcycle', 'bus']),
            )
            count += 1
    return jsonify({'success': True, 'events_seeded': count}), 200


# ==========================================================================
# Analytics API Routes
# ==========================================================================

@app.route('/api/analytics/dashboard', methods=['GET'])
def analytics_dashboard():
    """Returns all analytics data in one call for the analytics page."""
    return jsonify(analytics_engine.get_full_dashboard()), 200


@app.route('/api/analytics/heatmap', methods=['GET'])
def analytics_heatmap():
    """Returns heatmap intensity data per camera node."""
    hours = request.args.get('hours', default=24, type=int)
    return jsonify({'success': True, 'data': analytics_engine.get_heatmap_data(hours)}), 200


@app.route('/api/analytics/flow', methods=['GET'])
def analytics_flow():
    """Returns hourly vehicle flow trend data."""
    hours = request.args.get('hours', default=24, type=int)
    return jsonify({'success': True, 'data': analytics_engine.get_flow_trends(hours)}), 200


@app.route('/api/analytics/od_matrix', methods=['GET'])
def analytics_od():
    """Returns origin-destination movement matrix."""
    hours = request.args.get('hours', default=24, type=int)
    return jsonify({'success': True, 'data': analytics_engine.get_od_matrix(hours)}), 200


@app.route('/api/analytics/speed', methods=['GET'])
def analytics_speed():
    """Returns inter-camera speed estimates."""
    return jsonify({'success': True, 'data': analytics_engine.get_speed_estimates()}), 200


@app.route('/api/analytics/congestion', methods=['GET'])
def analytics_congestion():
    """Returns congested camera nodes."""
    return jsonify({'success': True, 'data': analytics_engine.get_congestion_nodes()}), 200


# ==========================================================================
# Alert System API Routes
# ==========================================================================

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Returns active (unresolved) alerts and summary."""
    limit = request.args.get('limit', default=30, type=int)
    return jsonify({
        'success': True,
        'alerts': alert_engine.get_active_alerts(limit),
        'all_alerts': alert_engine.get_all_alerts(limit),
        'summary': alert_engine.get_alert_summary(),
    }), 200


@app.route('/api/alerts/resolve/<int:alert_id>', methods=['POST'])
def resolve_alert(alert_id):
    """Marks an alert as resolved."""
    ok = alert_engine.resolve_alert(alert_id)
    return jsonify({'success': ok}), 200


@app.route('/api/alerts/summary', methods=['GET'])
def alert_summary():
    """Returns alert count summary for nav badge."""
    return jsonify(alert_engine.get_alert_summary()), 200


@app.route('/api/blacklist', methods=['GET'])
def get_blacklist():
    """Returns all active blacklisted plates."""
    return jsonify({'success': True, 'blacklist': alert_engine.get_blacklist()}), 200


@app.route('/api/blacklist/add', methods=['POST'])
def add_to_blacklist():
    """Adds a plate to the blacklist."""
    data = request.get_json(silent=True) or {}
    plate = data.get('plate', '').strip()
    reason = data.get('reason', 'Flagged by Operator')
    if not plate:
        return jsonify({'success': False, 'message': 'Plate number is required.'}), 400
    ok, msg = alert_engine.add_to_blacklist(plate, reason)
    return jsonify({'success': ok, 'message': msg}), (200 if ok else 400)


@app.route('/api/blacklist/remove/<plate>', methods=['DELETE'])
def remove_from_blacklist(plate):
    """Removes a plate from the blacklist."""
    ok, msg = alert_engine.remove_from_blacklist(plate)
    return jsonify({'success': ok, 'message': msg}), 200


@app.route('/api/blacklist/check/<plate>', methods=['GET'])
def check_blacklist(plate):
    """Checks if a specific plate is blacklisted."""
    is_bl = alert_engine.is_blacklisted(plate)
    return jsonify({'plate': plate, 'blacklisted': is_bl}), 200


if __name__ == '__main__':
    print("=" * 70)
    print("[CITY AI] City-Wide ANPR Intelligence Platform")
    print(f"[SERVER] Running on: http://{config.HOST}:{config.PORT}")
    print("=" * 70)
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, threaded=True)

