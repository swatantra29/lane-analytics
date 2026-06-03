# Threaded non-blocking video I/O
import cv2
import threading
import queue
import time


class ThreadedVideoStream:
    """
    Decoupled frame capture class operating on a separate daemon thread
    to completely eliminate video decoding blocking time from the execution loop.

    Frame pacing: the capture worker reads at the video's native FPS so that
    a 30 FPS source plays back in real-time rather than as fast as the disk
    can deliver frames.
    """

    def __init__(self, source_path: str, buffer_size: int = 8, loop: bool = False):
        self.stream = cv2.VideoCapture(source_path)
        if not self.stream.isOpened():
            raise IOError(f"Failed to open video source layer: {source_path}")

        # Read native FPS; fall back to 30 if the container doesn't report it
        native_fps = self.stream.get(cv2.CAP_PROP_FPS)
        self._frame_interval = 1.0 / native_fps if native_fps > 0 else 1.0 / 30.0

        # Smaller buffer (8 frames) prevents the queue from pre-filling with
        # a full second of frames before the pipeline even starts consuming.
        self.frame_queue = queue.Queue(maxsize=buffer_size)
        self.stopped = False
        self.frame_id = 0
        self.loop = loop

    def start(self):
        worker_thread = threading.Thread(target=self._capture_worker, args=())
        worker_thread.daemon = True
        worker_thread.start()
        return self

    def _capture_worker(self):
        next_read_at = time.perf_counter()

        while not self.stopped:
            # ── Rate-limit to native FPS ──────────────────────────────────
            now = time.perf_counter()
            sleep_for = next_read_at - now
            if sleep_for > 0:
                time.sleep(sleep_for)
            next_read_at = time.perf_counter() + self._frame_interval

            # ── Read one frame ────────────────────────────────────────────
            grabbed, frame = self.stream.read()
            if not grabbed:
                if self.loop:
                    self.stream.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    next_read_at = time.perf_counter() + self._frame_interval
                    continue
                self.stop()
                return

            self.frame_id += 1

            # If the pipeline is running behind, drop the oldest queued frame
            # and insert the new one — always keep the queue current.
            if self.frame_queue.full():
                try:
                    self.frame_queue.get_nowait()  # discard stale frame
                except queue.Empty:
                    pass

            self.frame_queue.put((self.frame_id, frame))

    def read_frame(self):
        try:
            return self.frame_queue.get(timeout=1.0)
        except queue.Empty:
            return None, None

    def stop(self):
        self.stopped = True
        if self.stream.isOpened():
            self.stream.release()
