import os

# Base Directory of the Project
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# YOLO AI Model Settings
MODEL_DIR = os.path.join(BASE_DIR, 'models')
MODEL_NAME = 'yolov8n.pt'  # Lightweight YOLOv8 nano model suitable for laptops
MODEL_PATH = os.path.join(MODEL_DIR, MODEL_NAME)
CONFIDENCE_THRESHOLD = 0.45  # Ignore detections with confidence below 45%

# Target vehicle COCO class names to count
TARGET_VEHICLE_CLASSES = ['car', 'motorcycle', 'bus', 'truck']

# Video Settings
VIDEO_DIR = os.path.join(BASE_DIR, 'videos')
UPLOAD_DIR = os.path.join(VIDEO_DIR, 'uploads')
DEFAULT_VIDEO_NAME = 'traffic.mp4'
DEFAULT_VIDEO_PATH = os.path.join(VIDEO_DIR, DEFAULT_VIDEO_NAME)

# 4-Lane Dedicated Video Inputs (North, East, South, West)
LANE_NAMES = ['North', 'East', 'South', 'West']
LANE_VIDEO_PATHS = {
    'North': os.path.join(VIDEO_DIR, 'lane_north.mp4'),
    'East':  os.path.join(VIDEO_DIR, 'lane_east.mp4'),
    'South': os.path.join(VIDEO_DIR, 'lane_south.mp4'),
    'West':  os.path.join(VIDEO_DIR, 'lane_west.mp4'),
}

# Video Processing Resolution (resize frames for performance on laptops)
PROCESS_WIDTH = 640   # Width in pixels to resize captured frames
PROCESS_HEIGHT = 360  # Height in pixels

# MJPEG Stream Settings (frames per second pushed to browser)
STREAM_FPS = 15       # Keep low for smooth browser rendering without high CPU

# Database Settings
DATABASE_DIR = os.path.join(BASE_DIR, 'database')
DATABASE_PATH = os.path.join(DATABASE_DIR, 'traffic.db')

# Signal Optimization Parameters
BASE_GREEN_TIME = 15       # Minimum base green light duration (seconds)
SEC_PER_VEHICLE = 2         # Additional green light seconds added per detected vehicle
MIN_GREEN_TIME = 15        # Hard lower bound for green light (seconds)
MAX_GREEN_TIME = 60        # Hard upper bound for green light (seconds)
YELLOW_LIGHT_TIME = 3      # Yellow light duration during signal transition (seconds)
AVG_CLEARANCE_RATE = 2.0   # Estimated seconds to clear 1 PCU in queue

# Lane Density Thresholds (Vehicle Count per Lane)
DENSITY_THRESHOLDS = {
    'LOW': (0, 5),          # 0 to 5 vehicles
    'MEDIUM': (6, 12),      # 6 to 12 vehicles
    'HIGH': (13, 20),       # 13 to 20 vehicles
    'VERY_HIGH': (21, 999) # 21 or more vehicles
}

# Flask Application Settings
HOST = '127.0.0.1'
PORT = 5000
DEBUG = True

