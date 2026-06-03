# Software Requirements Specification (SRS): Continuous Video Analytics Pipeline

## 1. System Architecture
### 1.1 Video I/O Module (Producer)
* **Function:** A dedicated daemon thread utilizing OpenCV `VideoCapture` to read frames into a bounded FIFO queue.
* **Purpose:** Decouples hardware I/O latency from the processing loop to prevent frame dropping.

### 1.2 Vision Pipeline (Consumer)
* **Distortion Correction:** Applies camera matrix coefficients to correct radial and tangential lens distortion.
* **Perspective Transform:** Computes a homography matrix to warp the region of interest (ROI) into a top-down "bird's-eye" view.
* **Binarization:** Fuses Sobel gradient magnitude (x-direction) with HLS (S-channel) color thresholding to isolate lane pixels robustly against varying light conditions.
* **Spatial Tracking:** Implements a sliding window polynomial fit to locate lane boundaries. Utilizes historical frame data to narrow the search space on subsequent frames.

### 1.3 Telemetry & Analytics Module
* **Function:** Aggregates calculated road curvature (in meters) and vehicle center offset.
* **Implementation:** Utilizes Polars for high-performance in-memory data aggregation and periodic batch writing to Parquet format.

## 2. Non-Functional Requirements
* **Latency:** The vision pipeline must process 1080p frames at >= 30 FPS.
* **Resource Utilization:** CPU utilization must be optimized via vectorization (NumPy) for matrix operations.
* **Extensibility:** The pipeline must be modular to allow the classical CV thresholding block to be swapped with a segmentation model (e.g., ONNX-compiled U-Net) in the future.

## 3. Data Output Contract
* Emits a serialized JSON payload per frame over IPC/WebSockets containing:
  `{ "frame_id": int, "radius_of_curvature": float, "center_offset": float, "processing_time_ms": float }`

## 4. Frontend Visualization
* **Primary HUD:** High-refresh canvas rendering the original video stream overlaid with the calculated inverse-perspective lane boundary polygon.
* **Telemetry Display:** Real-time tickers rendering calculated radius of curvature in meters and horizontal vehicle drift from the lane center line in meters.
