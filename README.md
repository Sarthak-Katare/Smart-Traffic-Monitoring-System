# Smart Traffic Optimization Using AI

> **B.Tech 2nd-Year IT Macro Project**  
> Real-Time Computer Vision & Artificial Intelligence Based Dynamic Traffic Signal Control System

---

## 📌 Project Overview

**Smart Traffic Optimization Using AI** is a full-stack computer vision application designed to optimize urban traffic intersection signal timings dynamically. Traditional traffic signals operate on fixed time intervals regardless of actual vehicle flow, leading to unnecessary delays, fuel waste, and traffic congestion.

This system uses **YOLOv8** (Ultralytics) and **OpenCV** to analyze live traffic camera feeds, count vehicle types (Cars, Motorcycles, Buses, Trucks), determine lane traffic density, and calculate dynamic green-light durations with a fairness mechanism to prevent lane starvation.

---

## 🛠️ Technology Stack

* **Programming Language:** Python 3.10+
* **AI / Computer Vision:** YOLOv8 (Ultralytics), OpenCV, NumPy
* **Web Backend:** Flask (Python)
* **Web Frontend:** HTML5, CSS3 (Vanilla Dark Mode), JavaScript (ES6), Chart.js
* **Database:** SQLite3
* **Development Environment:** VS Code / Antigravity

---

## 📁 Project Architecture & Directory Structure

```text
SmartTrafficAI/
├── app.py                      # Flask Application Server Entrypoint
├── config.py                   # Central Configuration File
├── requirements.txt            # Python Package Dependencies
├── README.md                   # Project Documentation
├── models/
│   └── README.md               # YOLO Model Weights Storage (yolov8n.pt)
├── videos/
│   └── README.md               # Input Traffic Videos (traffic.mp4)
├── detection/
│   └── __init__.py             # Computer Vision & Detection Package
├── traffic/
│   └── __init__.py             # Density & Signal Optimization Engine
├── database/
│   └── __init__.py             # SQLite Database Layer
├── utils/
│   └── __init__.py             # Helper Utilities
├── templates/
│   ├── index.html              # Main Dashboard Template
│   └── history.html            # Historical Logs & Analysis Page
├── static/
│   ├── css/
│   │   └── style.css           # Glassmorphic Dark UI Styling
│   └── js/
│       └── dashboard.js        # Dashboard UI Polling & Chart.js Logic
└── tests/
    └── __init__.py             # Automated Testing Suite
```

---

## 🚀 How to Setup and Run (Phase 1)

### 1. Open Terminal in Project Directory
Ensure your terminal is in the project root folder:
```powershell
cd "c:\Users\sus\OneDrive\Desktop\Smart Trafic Monetiring System"
```

### 2. Create Python Virtual Environment (Recommended)
```powershell
python -m venv venv
```

Activate the virtual environment:
- **Windows (PowerShell):**
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
- **Windows (CMD):**
  ```cmd
  .\venv\Scripts\activate.bat
  ```

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Run the Flask Web Application
```powershell
python app.py
```

### 5. Access the Web Dashboard
Open your web browser and navigate to:
```text
http://127.0.0.1:5000
```

---

## 🔍 API Endpoints (Phase 1)

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | Main Smart Traffic AI Dashboard |
| `/history` | `GET` | Historical Logs & Analytics Page |
| `/api/health` | `GET` | Server Health Status JSON |
| `/api/status` | `GET` | System Configuration & Asset Status JSON |
| `/api/stats` | `GET` | Current Live Statistics JSON |

---

## 🛣️ 12-Phase Development Roadmap

- [x] **Phase 1:** Project Setup, Folder Structure, Config, Flask App, & Dashboard UI Shell
- [ ] **Phase 2:** OpenCV Video Processing Engine & Video Reader
- [ ] **Phase 3:** YOLOv8 Object Detection Engine Integration (`yolov8n.pt`)
- [ ] **Phase 4:** Vehicle Tracking & Anti-Double-Counting Tracker
- [ ] **Phase 5:** 4-Way Lane Region Selection & Spatial Analysis
- [ ] **Phase 6:** Traffic Density Classification Engine
- [ ] **Phase 7:** Dynamic Green-Light Optimization Algorithm & Fairness Mechanism
- [ ] **Phase 8:** Software Traffic Signal State Machine Simulation
- [ ] **Phase 9:** SQLite Database Storage & Query API
- [ ] **Phase 10:** Live Video Streaming Over Web Dashboard
- [ ] **Phase 11:** Automated Testing & Validation Suite
- [ ] **Phase 12:** Project Finalization, Documentation & Presentation Polish
