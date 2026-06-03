# Core entry point and orchestration loop
"""
main.py — Dual-mode entry point:
  1. Headless WebSocket server (default): streams JPEG frames + JSON telemetry
     to the decoupled browser frontend over a single asyncio WebSocket connection.
  2. Local OpenCV window (--local flag): original debug mode with cv2.imshow.

WebSocket message protocol — ONE JSON text message per frame:
  {
    "type": "frame",
    "jpeg_b64": "<base64-encoded JPEG string>",
    "telemetry": {
      "frame_id": int,
      "radius_of_curvature": float,
      "center_offset": float,
      "processing_time_ms": float,
      "timestamp": float
    }
  }
"""

import asyncio
import base64
import json
import os
import sys
import time
import threading
import argparse

import cv2
import numpy as np
import websockets
from websockets.server import WebSocketServerProtocol

from pipeline.stream import ThreadedVideoStream
from pipeline.vision import VisionProcessor
from pipeline.tracker import LaneTracker
from analytics.logger import HighThroughputLogger

# ──────────────────────────────────────────────────────────────────────────────
# Shared state between pipeline thread and WebSocket broadcast loop
# ──────────────────────────────────────────────────────────────────────────────
_latest_frame_bytes: bytes | None = None   # JPEG bytes of most recent overlay
_latest_telemetry: dict | None = None      # Most recent telemetry dict
_pipeline_done = threading.Event()
_pipeline_paused = threading.Event()
_pipeline_paused.set()  # Start in running state (set = not paused)
_state_lock = threading.Lock()

# Connected WebSocket clients (written/read only from the asyncio event loop)
_connected_clients: set[WebSocketServerProtocol] = set()
# NOTE: _clients_lock is created inside _serve() to avoid the asyncio event-loop
# requirement that locks be created inside a running loop (Python 3.10+ deprecation,
# hard error in 3.12+).  All coroutines that need it receive it as a parameter.
_clients_lock: asyncio.Lock | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline thread (runs in background, fills shared state)
# ──────────────────────────────────────────────────────────────────────────────

def _pipeline_worker(video_source: str, logger: HighThroughputLogger, loop: bool = False) -> None:
    """
    Runs the full CV pipeline synchronously on a background thread so that it
    does not block the asyncio event loop driving the WebSocket server.
    """
    global _latest_frame_bytes, _latest_telemetry

    try:
        streamer = ThreadedVideoStream(source_path=video_source, loop=loop).start()
    except IOError as exc:
        print(f"[Pipeline] {exc}", file=sys.stderr)
        _pipeline_done.set()
        return

    frame_w = int(streamer.stream.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(streamer.stream.get(cv2.CAP_PROP_FRAME_HEIGHT))

    processor = VisionProcessor(frame_width=frame_w, frame_height=frame_h)
    tracker = LaneTracker(frame_height=frame_h, frame_width=frame_w)

    print(f"[Pipeline] Stream opened — {frame_w}x{frame_h}")

    try:
        while not streamer.stopped:
            # ── Pause gate ────────────────────────────────────────────────
            # Blocks here (no CPU spin) when frontend sends 'pause'.
            _pipeline_paused.wait()

            t0 = time.perf_counter()
            frame_id, raw_frame = streamer.read_frame()

            if raw_frame is None:
                break

            # ── Vision stages ──────────────────────────────────────────────
            binary_mask = processor.generate_binary_mask(raw_frame)
            warped_binary = processor.project_to_birds_eye(binary_mask)
            left_fit, right_fit, radius, offset = tracker.fit_lanes(warped_binary)

            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.record_metrics(frame_id, radius, offset, latency_ms)

            # ── Build overlay image ────────────────────────────────────────
            if left_fit is not None and right_fit is not None:
                overlay = tracker.build_overlay_frame(
                    raw_frame, warped_binary, left_fit, right_fit, processor
                )
                # Render HUD text on overlay
                cv2.putText(overlay, f"Radius: {radius:.1f} m", (50, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.putText(overlay, f"Offset: {offset:+.2f} m", (50, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
            else:
                overlay = raw_frame

            jpeg_bytes = processor.encode_frame_jpeg(overlay)

            telemetry = {
                "frame_id": frame_id,
                "radius_of_curvature": round(radius, 2),
                "center_offset": round(offset, 4),
                "processing_time_ms": round(latency_ms, 2),
                "timestamp": time.time(),
            }

            # ── Write to shared state (non-blocking) ───────────────────────
            with _state_lock:
                _latest_frame_bytes = jpeg_bytes
                _latest_telemetry = telemetry

    finally:
        streamer.stop()
        os.makedirs("data", exist_ok=True)
        logger.commit_to_disk()
        _pipeline_done.set()
        print("[Pipeline] Shutdown complete.")


# ──────────────────────────────────────────────────────────────────────────────
# AsyncIO broadcast task — pushes latest state to all connected WebSocket clients
# ──────────────────────────────────────────────────────────────────────────────

async def _broadcast_loop(target_fps: int = 30) -> None:
    """
    Polls the shared state at `target_fps` and broadcasts to all clients.
    Each tick sends:
      1. Binary JPEG frame (for <img> src replacement on the frontend)
      2. JSON text telemetry payload
    """
    interval = 1.0 / target_fps

    while not _pipeline_done.is_set():
        await asyncio.sleep(interval)

        with _state_lock:
            frame_bytes = _latest_frame_bytes
            telemetry = _latest_telemetry

        if frame_bytes is None or telemetry is None:
            continue

        # Encode frame as base64 so it fits cleanly inside a single JSON envelope
        b64_frame = base64.b64encode(frame_bytes).decode("ascii")
        envelope = {
            "type": "frame",
            "jpeg_b64": b64_frame,
            "telemetry": telemetry,
        }
        message = json.dumps(envelope)

        if _connected_clients:
            # Fire-and-forget to all connected sockets; skip slow clients
            await asyncio.gather(
                *[_safe_send(ws, message) for ws in list(_connected_clients)],
                return_exceptions=True,
            )


async def _safe_send(ws: WebSocketServerProtocol, message: str) -> None:
    try:
        await ws.send(message)
    except Exception:
        pass  # Client disconnected; _ws_handler will remove it


# ──────────────────────────────────────────────────────────────────────────────
# WebSocket connection handler
# ──────────────────────────────────────────────────────────────────────────────

async def _ws_handler(ws: WebSocketServerProtocol) -> None:
    peer = ws.remote_address
    print(f"[WS] Client connected: {peer}")

    assert _clients_lock is not None
    async with _clients_lock:
        _connected_clients.add(ws)

    # Send the current pause state so the frontend button syncs on connect
    init_msg = json.dumps({"type": "status", "paused": not _pipeline_paused.is_set()})
    await _safe_send(ws, init_msg)

    try:
        # Listen for incoming control messages while the connection is open
        async for raw in ws:
            try:
                msg = json.loads(raw)
                if msg.get("type") == "control":
                    action = msg.get("action")
                    if action == "pause":
                        _pipeline_paused.clear()
                        print("[Pipeline] Paused by client.")
                        # Broadcast new status to all clients
                        status_msg = json.dumps({"type": "status", "paused": True})
                        await asyncio.gather(
                            *[_safe_send(c, status_msg) for c in list(_connected_clients)],
                            return_exceptions=True,
                        )
                    elif action == "resume":
                        _pipeline_paused.set()
                        print("[Pipeline] Resumed by client.")
                        status_msg = json.dumps({"type": "status", "paused": False})
                        await asyncio.gather(
                            *[_safe_send(c, status_msg) for c in list(_connected_clients)],
                            return_exceptions=True,
                        )
            except (json.JSONDecodeError, KeyError):
                pass
    finally:
        async with _clients_lock:
            _connected_clients.discard(ws)
        print(f"[WS] Client disconnected: {peer}")


# ──────────────────────────────────────────────────────────────────────────────
# Local debug mode (no WebSocket, uses cv2.imshow instead)
# ──────────────────────────────────────────────────────────────────────────────

def _run_local(video_source: str) -> None:
    logger = HighThroughputLogger()

    try:
        streamer = ThreadedVideoStream(source_path=video_source).start()
    except IOError as exc:
        print(f"[Error] {exc}", file=sys.stderr)
        return

    frame_w = int(streamer.stream.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(streamer.stream.get(cv2.CAP_PROP_FRAME_HEIGHT))

    processor = VisionProcessor(frame_width=frame_w, frame_height=frame_h)
    tracker = LaneTracker(frame_height=frame_h, frame_width=frame_w)

    print(f"[Local] Stream opened — {frame_w}x{frame_h}. Press 'q' to quit.")

    try:
        while not streamer.stopped:
            t0 = time.perf_counter()
            frame_id, raw_frame = streamer.read_frame()

            if raw_frame is None:
                break

            binary_mask = processor.generate_binary_mask(raw_frame)
            warped_binary = processor.project_to_birds_eye(binary_mask)
            left_fit, right_fit, radius, offset = tracker.fit_lanes(warped_binary)

            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.record_metrics(frame_id, radius, offset, latency_ms)

            if left_fit is not None and right_fit is not None:
                overlay = tracker.build_overlay_frame(
                    raw_frame, warped_binary, left_fit, right_fit, processor
                )
                cv2.putText(overlay, f"Radius: {radius:.1f} m", (50, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.putText(overlay, f"Offset: {offset:+.2f} m", (50, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.imshow("Lane Tracking — Local Debug", overlay)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        streamer.stop()
        cv2.destroyAllWindows()
        os.makedirs("data", exist_ok=True)
        logger.commit_to_disk()


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

async def _serve(host: str, port: int, video_source: str, loop: bool = False) -> None:
    global _clients_lock
    # Create the asyncio Lock inside the running event loop (required Python 3.10+)
    _clients_lock = asyncio.Lock()

    logger = HighThroughputLogger()

    # Start pipeline on a background thread so asyncio loop is not blocked
    pipeline_thread = threading.Thread(
        target=_pipeline_worker, args=(video_source, logger, loop), daemon=True
    )
    pipeline_thread.start()

    print(f"[Server] WebSocket server listening on ws://{host}:{port}")

    async with websockets.serve(_ws_handler, host, port):
        # Run broadcast loop concurrently until pipeline finishes
        await _broadcast_loop()

    pipeline_thread.join(timeout=5)
    print("[Server] Shutdown.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Lane Analytics Pipeline Server")
    parser.add_argument(
        "--source", default="data/source_video.mp4",
        help="Path to input dashcam video file"
    )
    parser.add_argument(
        "--local", action="store_true",
        help="Run in local OpenCV window mode instead of WebSocket server"
    )
    parser.add_argument(
        "--loop", action="store_true",
        help="Loop the source video (useful for testing with short clips)"
    )
    parser.add_argument("--host", default="localhost", help="WebSocket server host")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket server port")
    args = parser.parse_args()

    if not os.path.exists(args.source):
        print(f"[Error] Missing input video at: {args.source}", file=sys.stderr)
        print("Place a dashcam MP4 at that path and re-run.", file=sys.stderr)
        sys.exit(1)

    if args.local:
        _run_local(args.source)
    else:
        asyncio.run(_serve(args.host, args.port, args.source, args.loop))


if __name__ == "__main__":
    main()
