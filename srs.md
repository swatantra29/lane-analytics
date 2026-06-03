# Software Requirements Specification — Lane Analytics Frontend
## 1. Purpose & Scope
This document specifies the complete requirements for the **Lane Analytics Dashboard** — a
decoupled, browser-based frontend that visualises real-time output from the Python CV pipeline
served over WebSocket (`ws://localhost:8765`).
The frontend must connect to the backend WebSocket server, render a live lane-annotated video
feed, display telemetry gauges, and chart historical metrics — all with zero server-side
rendering and no build step (plain HTML + Vanilla CSS + Vanilla JS).
---
## 2. Architecture Overview
```
Browser
  │
  ├── index.html          Root shell, imports CSS and JS modules
  ├── css/
  │   └── style.css       Design system — tokens, layout, components
  └── js/
      ├── ws.js           WebSocket connection manager + message parser
      ├── video.js        Canvas renderer for JPEG frame stream
      ├── telemetry.js    Live gauge / ticker updaters
      └── chart.js        Rolling time-series chart (curvature + offset)
```
The backend pushes a **single JSON text message per processed frame**:
```json
{
  "type": "frame",
  "jpeg_b64": "<base64-encoded JPEG string>",
  "telemetry": {
    "frame_id": 1042,
    "radius_of_curvature": 512.30,
    "center_offset": -0.12,
    "processing_time_ms": 18.4,
    "timestamp": 1717430400.123
  }
}
```
The frontend decodes `jpeg_b64` and renders it on a `<canvas>` element, then routes the
`telemetry` object to the gauge and chart subsystems.
---
## 3. Page Structure — `index.html`
The single page is divided into three visual regions:
### 3.1 Header / Navbar
- App logo (SVG or text mark): **"Lane Analytics"**
- Status pill: shows `CONNECTING` (amber), `LIVE` (green), or `DISCONNECTED` (red)
- Dark-mode only design; no light mode toggle required
### 3.2 Main Content Grid (two-column on ≥ 1024 px, single-column on mobile)
**Column A — Video Panel**
- A `<canvas id="videoCanvas">` filling the panel at the native aspect ratio of the stream
  (typically 16:9). The canvas must scale responsively.
- Overlay badge in the top-right corner showing the current `frame_id`.
- A semi-transparent frosted-glass card anchored at the bottom of the canvas showing the
  two primary HUD values inline:
  - **Radius of Curvature** — value in meters
  - **Center Offset** — value in meters with sign (+/-)
**Column B — Telemetry Panel**
- Three large gauge/stat cards stacked vertically:
  1. **Curvature Gauge** — displays `radius_of_curvature` in meters. Use a circular SVG arc
     gauge. Range: 0 – 3000 m. Color band: green (> 1000 m straight), amber (300–1000 m),
     red (< 300 m sharp curve).
  2. **Offset Ticker** — displays `center_offset` in meters. Positive = drifting right,
     negative = drifting left. Show a horizontal bar centered at 0, range ±1.5 m.
     Color: green when |offset| < 0.3 m, amber < 0.6 m, red ≥ 0.6 m.
  3. **Latency Card** — displays `processing_time_ms` in milliseconds. Show a simple numeric
     readout with a mini sparkline of the last 60 values.
### 3.3 Chart Section (below the two-column grid)
- A full-width time-series chart rendered on a `<canvas id="metricsChart">`.
- Two datasets plotted together:
  - **Curvature (m)** — left Y-axis, blue line
  - **Offset (m)** — right Y-axis, orange line
- Rolling window of the **last 300 frames**; oldest data scrolls off the left edge.
- X-axis: frame numbers (integers).
- Chart must be drawn in pure Canvas 2D API — **no Chart.js or any external charting library**.
- Grid lines, axis labels, and a legend are required.
---
## 4. WebSocket Client — `js/ws.js`
- Export a class `LaneWSClient(url, onMessage)`.
- Automatically reconnects with exponential backoff (max 30 s delay) on disconnect.
- Parses incoming text message as JSON and invokes `onMessage(parsed)`.
- Exposes a `status` property: `"connecting" | "live" | "disconnected"`.
- Dispatches a custom DOM event `ws-status-change` on the document whenever status changes,
  so the header pill can update independently.
---
## 5. Canvas Video Renderer — `js/video.js`
- Export a class `VideoRenderer(canvasId)`.
- Method `renderFrame(base64JpegString)`:
  - Creates an `Image` object, sets `src = "data:image/jpeg;base64," + base64JpegString`.
  - On `image.onload`, `drawImage` to canvas, scaling to fill while preserving aspect ratio
    (letterbox / pillarbox with `#0a0a0f` fill on margins).
- Must be non-blocking — never stalls the main thread waiting for decode.
---
## 6. Telemetry Updaters — `js/telemetry.js`
- Export a class `TelemetryDisplay`.
- Method `update(telemetry)` — receives the `telemetry` sub-object from the WS message and
  updates all three gauge/stat cards.
- **Curvature SVG arc gauge**: compute the fill angle from 0–360° mapped to 0–3000 m,
  update `stroke-dasharray` on an SVG `<circle>` element, and transition smoothly with CSS
  `transition: stroke-dasharray 0.15s ease`.
- **Offset bar**: update a CSS custom property `--offset-pct` on the bar element, which
  controls `translateX`. Animate with CSS transition.
- **Latency sparkline**: maintain an internal ring buffer of 60 values; redraw a small
  `<canvas>` sparkline on every `update` call.
---
## 7. Metrics Chart — `js/chart.js`
- Export a class `MetricsChart(canvasId)`.
- Internal state: two circular arrays of length 300 for curvature and offset values, plus a
  corresponding frame ID array.
- Method `push(frameId, curvature, offset)` — appends data and triggers a redraw.
- `draw()` method uses Canvas 2D API:
  - Clear canvas.
  - Draw dark background `#0f0f18` and a subtle grid (`#ffffff0d` lines).
  - Draw curvature polyline (blue `#4dabf7`) on left Y-axis (0–3000 m).
  - Draw offset polyline (orange `#ff9f40`) on right Y-axis (−1.5 to +1.5 m).
  - Draw X-axis frame labels every 50 frames.
  - Draw Y-axis labels and a two-entry legend in the top-right corner.
- `draw()` is called via `requestAnimationFrame` for smooth 60-fps redraws independent of WS
  message rate.
---
## 8. Design System — `css/style.css`
### 8.1 Color Tokens (CSS Custom Properties)
```css
--bg-primary:       #0a0a0f;  /* Page background */
--bg-surface:       #13131f;  /* Card backgrounds */
--bg-surface-2:     #1c1c2e;  /* Nested surfaces */
--accent-blue:      #4dabf7;
--accent-orange:    #ff9f40;
--accent-green:     #69db7c;
--accent-amber:     #fcc419;
--accent-red:       #ff6b6b;
--text-primary:     #e8eaf0;
--text-secondary:   #7c7f93;
--border-subtle:    #ffffff1a;
--glow-blue:        0 0 24px #4dabf730;
--radius-card:      16px;
--radius-pill:      999px;
```
### 8.2 Typography
- Import **Inter** from Google Fonts (weights 400, 500, 600, 700).
- Base font: `Inter, system-ui, sans-serif`.
- Numeric readouts (gauges, tickers): `font-variant-numeric: tabular-nums` to prevent layout
  shift as values change.
### 8.3 Layout
- Full-viewport dark background, no scroll on desktop.
- CSS Grid for the main two-column content area:
  ```
  grid-template-columns: 2fr 1fr   /* ≥ 1024 px */
  grid-template-columns: 1fr       /* < 1024 px  */
  ```
- Cards use `backdrop-filter: blur(12px)` for glassmorphism where layered over video.
### 8.4 Animations & Micro-interactions
- All gauge value transitions: CSS `transition` (150–200 ms ease).
- Card hover: `transform: translateY(-2px)` + subtle box-shadow glow increase (200 ms).
- Status pill: pulsing `@keyframes` ring animation when in `LIVE` state.
- Page load: cards fade in with staggered `animation-delay` (0 ms, 80 ms, 160 ms).
---
## 9. Functional Requirements
| ID   | Requirement |
|------|-------------|
| F-01 | The dashboard must establish a WebSocket connection to `ws://localhost:8765` on page load. |
| F-02 | Frames must be rendered on the canvas within 50 ms of receipt (excluding decode time). |
| F-03 | Telemetry gauges must update on every received message with no visible stutter. |
| F-04 | If the WebSocket disconnects, gauges must freeze at last-known values and the status pill switches to `DISCONNECTED`. Reconnect attempts happen automatically. |
| F-05 | The metrics chart must never exceed 300 buffered data points; oldest data is evicted. |
| F-06 | The page must be usable on screens ≥ 375 px wide (responsive layout). |
| F-07 | No external JS libraries may be used (no jQuery, no Chart.js, no React). Vanilla JS only. |
| F-08 | All interactive elements must have unique, descriptive `id` attributes. |
---
## 10. Non-Functional Requirements
| ID    | Requirement |
|-------|-------------|
| NF-01 | JS main thread must not block for > 16 ms to maintain 60-fps canvas updates. |
| NF-02 | JPEG decode must be done via `Image.onload` (browser-native, off main thread). |
| NF-03 | The frontend must work without any server (open `index.html` directly from the filesystem via `file://`), except for the live WS connection which requires the backend to be running. |
| NF-04 | No build step, no bundler, no npm. Single HTML file with `<script type="module">` imports. |
---
## 11. File Responsibility Summary
| File | Responsibility |
|------|----------------|
| `index.html` | DOM structure; links CSS; imports JS modules; defines all element IDs |
| `css/style.css` | Complete design system: tokens, layout, components, animations |
| `js/ws.js` | WebSocket lifecycle, reconnection, status events |
| `js/video.js` | Canvas JPEG frame rendering, aspect-ratio scaling |
| `js/telemetry.js` | Gauge/ticker/sparkline update logic |
| `js/chart.js` | Full-width rolling time-series chart via Canvas 2D API |
---
## 12. Acceptance Criteria
1. Opening `index.html` in a browser while `main.py` is running shows a live annotated video feed.
2. All three telemetry cards update in real time as frames arrive.
3. The metrics chart scrolls smoothly with incoming data.
4. Closing the backend causes the status pill to change to `DISCONNECTED` within 2 seconds and the dashboard reconnects automatically when the backend restarts.
5. The UI is fully readable on a 375 px mobile viewport.