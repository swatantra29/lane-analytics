# Lane Analytics

A real-time computer vision pipeline that detects lane boundaries from dashcam footage and streams annotated video frames and telemetry to a live browser dashboard over WebSocket.

```
lane_analytics/
├── backend/            Python CV pipeline + WebSocket server
│   ├── main.py         Entry point (dual-mode: server / local window)
│   ├── pipeline/
│   │   ├── stream.py   Threaded non-blocking video I/O
│   │   ├── vision.py   Sobel/HLS binarization + perspective warp
│   │   └── tracker.py  Sliding-window polynomial lane fitting
│   └── analytics/
│       └── logger.py   In-memory Polars buffer → Parquet on shutdown
├── frontend/           React + Vite + TailwindCSS dashboard
│   └── src/
│       ├── lib/ws.ts   WebSocket client (auto-reconnect, exp. backoff)
│       └── components/ Video canvas, curvature gauge, offset bar, chart
├── data/
│   ├── source_video.mp4        Input dashcam footage (place yours here)
│   └── calibration_cache.json  Camera intrinsics (future use)
├── venv/               Python virtual environment
└── requirements.txt    Python dependencies
```

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.10+ |
| Node.js | 18+ |
| npm | 9+ |

---

## Setup

### 1. Python backend

```bash
cd lane_analytics

# Install dependencies into the venv
venv/bin/python -m pip install -r requirements.txt
```

### 2. Frontend

```bash
cd lane_analytics/frontend
npm install
```

### 3. Add your video

Place a dashcam MP4 at:

```
lane_analytics/data/source_video.mp4
```

---

## Running the App

You need **two terminals** running simultaneously.

### Terminal 1 — Python backend

```bash
cd lane_analytics
venv/bin/python ./backend/main.py --source ./data/source_video.mp4
```

> For short test clips that you want to loop continuously:
> ```bash
> venv/bin/python ./backend/main.py --source ./data/source_video.mp4 --loop
> ```

**Expected output:**
```
[Server] WebSocket server listening on ws://localhost:8765
[Pipeline] Stream opened — 1280x720
```

### Terminal 2 — Frontend dev server

```bash
cd lane_analytics/frontend
npm run dev
```

Then open **http://localhost:3000** in your browser.

---

## CLI Reference (backend)

```
venv/bin/python backend/main.py [OPTIONS]

Options:
  --source PATH   Path to input MP4 video        (default: data/source_video.mp4)
  --loop          Loop video on EOF (for testing with short clips)
  --local         Show output in an OpenCV window instead of WebSocket server
  --host HOST     WebSocket server host           (default: localhost)
  --port PORT     WebSocket server port           (default: 8765)
```

---

## Architecture

```
┌──────────────────────────────────────┐
│  Python Backend                      │
│                                      │
│  ThreadedVideoStream (daemon thread) │
│    └─ Bounded FIFO queue (128 frames)│
│         │                            │
│  _pipeline_worker (background thread)│
│    ├─ VisionProcessor                │
│    │   ├─ HLS/Sobel binarization     │
│    │   └─ Perspective warp (bird's-eye)│
│    ├─ LaneTracker                    │
│    │   ├─ Sliding-window fit         │
│    │   └─ Prior-cache targeted search│
│    └─ HighThroughputLogger           │
│         └─ Polars → Parquet on exit  │
│                                      │
│  asyncio WebSocket server (:8765)    │
│    └─ _broadcast_loop (30 fps push)  │
│         └─ JSON envelope per frame:  │
│            { type, jpeg_b64,         │
│              telemetry: { frame_id,  │
│              radius_of_curvature,    │
│              center_offset,          │
│              processing_time_ms } }  │
└──────────────────────────────────────┘
           WebSocket ws://localhost:8765
┌──────────────────────────────────────┐
│  React Frontend (:3000)              │
│                                      │
│  LaneWSClient (ws.ts)                │
│    └─ Auto-reconnect (exp. backoff)  │
│                                      │
│  VideoPanel   — canvas JPEG renderer │
│  CurvatureGauge — SVG arc gauge      │
│  OffsetTicker   — centered bar       │
│  LatencySparkline — ring-buffer plot │
│  MetricsChart — rolling time-series  │
└──────────────────────────────────────┘
```

---

## Data Output

On shutdown, the backend writes a Parquet file:

```
lane_analytics/data/telemetry_output.parquet
```

Schema:

| Column | Type | Description |
|--------|------|-------------|
| `frame_id` | Int64 | Sequential frame number |
| `timestamp` | Float64 | Unix epoch (seconds) |
| `radius_of_curvature_m` | Float64 | Estimated road curvature in meters |
| `center_offset_m` | Float64 | Vehicle offset from lane center (+ = right) |
| `latency_ms` | Float64 | Per-frame pipeline processing time |

Read it with:

```python
import polars as pl
df = pl.read_parquet("lane_analytics/data/telemetry_output.parquet")
print(df.describe())
```

---

## Known Warnings

| Warning | Cause | Impact |
|---------|-------|--------|
| `WebSocketServerProtocol is deprecated` | `websockets` v16 renamed the class | None — works correctly |
| `RankWarning: Polyfit may be poorly conditioned` | Frames where one lane is partially off-screen | Handled gracefully by fallback path |

---

## Performance (tested on 960×540 source)

| Metric | Value |
|--------|-------|
| Avg. pipeline latency | ~15–20 ms/frame |
| Throughput | ~50–65 FPS (pipeline), 30 FPS broadcast |
| JPEG frame size | ~32–40 KB at 75% quality |
