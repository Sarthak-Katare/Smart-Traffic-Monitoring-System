"""
video_splitter.py — Prepares 4 distinct demo lane videos for North, East, South, West lanes.
Generates clips with different temporal offsets, playback speeds, and regions so each lane
exhibits distinct traffic patterns.
"""

import os
import cv2
import config

LANE_NAMES = ['North', 'East', 'South', 'West']


def ensure_lane_videos():
    """
    Checks if lane_north.mp4, lane_east.mp4, lane_south.mp4, lane_west.mp4 exist in videos/.
    If any are missing, extracts 4 distinct variations from traffic.mp4.
    """
    os.makedirs(config.VIDEO_DIR, exist_ok=True)
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)

    missing = []
    for lane in LANE_NAMES:
        path = config.LANE_VIDEO_PATHS.get(lane)
        if not path or not os.path.exists(path):
            missing.append(lane)

    if not missing:
        print("[VIDEO ASSETS] All 4 lane video files are present.")
        return True

    source_path = config.DEFAULT_VIDEO_PATH
    if not os.path.exists(source_path):
        print(f"[VIDEO ASSETS] Source video {source_path} not found. Cannot generate lane clips.")
        return False

    print(f"[VIDEO ASSETS] Generating distinct video feeds for lanes: {missing} ...")

    cap = cv2.VideoCapture(source_path)
    if not cap.isOpened():
        print(f"[VIDEO ASSETS] Could not open {source_path}")
        return False

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')

    # Read all frames into memory (traffic.mp4 is small ~377 frames)
    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
    cap.release()

    if not frames:
        print("[VIDEO ASSETS] No frames read from source video.")
        return False

    n_frames = len(frames)

    # Define distinct temporal offsets and slicing configurations per lane
    lane_configs = {
        'North': {'offset': 0, 'step': 1, 'flip': False},
        'East':  {'offset': int(n_frames * 0.25), 'step': 1, 'flip': True},
        'South': {'offset': int(n_frames * 0.50), 'step': 1, 'flip': False},
        'West':  {'offset': int(n_frames * 0.75), 'step': 1, 'flip': True}
    }

    target_w = config.PROCESS_WIDTH
    target_h = config.PROCESS_HEIGHT

    for lane, cfg in lane_configs.items():
        out_path = config.LANE_VIDEO_PATHS[lane]
        if os.path.exists(out_path):
            continue

        writer = cv2.VideoWriter(out_path, fourcc, fps, (target_w, target_h))
        offset = cfg['offset']
        step = cfg['step']
        flip = cfg['flip']

        for i in range(0, n_frames, step):
            idx = (offset + i) % n_frames
            f = frames[idx].copy()
            if flip:
                f = cv2.flip(f, 1)  # Horizontal flip for varied perspective
            f_resized = cv2.resize(f, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
            writer.write(f_resized)

        writer.release()
        print(f"[VIDEO ASSETS] Created lane video: {out_path} ({n_frames} frames)")

    print("[VIDEO ASSETS] 4-lane video setup complete.")
    return True


if __name__ == '__main__':
    ensure_lane_videos()
