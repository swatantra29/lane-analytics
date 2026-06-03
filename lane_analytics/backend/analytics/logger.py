# In-memory data capture and Polars/Parquet IO
import polars as pl
import time
import os


class HighThroughputLogger:
    """
    Manages lock-free analytics capturing routines, structured with strict schema templates
    flushed directly to optimal analytical formats on system shutdown.
    """

    def __init__(self):
        self.schema = {
            "frame_id": pl.Int64,
            "timestamp": pl.Float64,
            "radius_of_curvature_m": pl.Float64,
            "center_offset_m": pl.Float64,
            "latency_ms": pl.Float64,
        }
        self.memory_buffer: list[dict] = []

    def record_metrics(
        self,
        frame_id: int,
        curvature: float,
        offset: float,
        execution_latency_ms: float,
    ) -> None:
        """Append one frame's telemetry record to the in-memory buffer."""
        self.memory_buffer.append({
            "frame_id": frame_id,
            "timestamp": time.time(),
            "radius_of_curvature_m": curvature,
            "center_offset_m": offset,
            "latency_ms": execution_latency_ms,
        })

    def latest_record(self) -> dict | None:
        """Return the most recently recorded telemetry row, or None if buffer is empty."""
        return self.memory_buffer[-1] if self.memory_buffer else None

    def rolling_stats(self, window: int = 30) -> dict:
        """
        Compute lightweight rolling statistics over the last `window` frames
        for real-time HUD display without building a full Polars DataFrame.
        """
        recent = self.memory_buffer[-window:]
        if not recent:
            return {"avg_curvature_m": 0.0, "avg_offset_m": 0.0, "avg_latency_ms": 0.0}

        avg_curv = sum(r["radius_of_curvature_m"] for r in recent) / len(recent)
        avg_off = sum(r["center_offset_m"] for r in recent) / len(recent)
        avg_lat = sum(r["latency_ms"] for r in recent) / len(recent)

        return {
            "avg_curvature_m": round(avg_curv, 2),
            "avg_offset_m": round(avg_off, 4),
            "avg_latency_ms": round(avg_lat, 2),
        }

    def commit_to_disk(self, target_filepath: str = "data/telemetry_output.parquet") -> None:
        """Flush the entire in-memory buffer to Parquet via Polars."""
        if not self.memory_buffer:
            print("[Warning] Execution buffer contains empty records. Operation skipped.")
            return

        # Ensure output directory exists before writing
        out_dir = os.path.dirname(target_filepath)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        # Explicitly build dataframe using highly optimized Polars memory layout
        telemetry_df = pl.DataFrame(self.memory_buffer, schema=self.schema)
        telemetry_df.write_parquet(target_filepath, compression="snappy")
        print(f"[Success] Processed record batches written to: {target_filepath}")
        print(telemetry_df.describe())