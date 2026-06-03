export interface Telemetry {
  frame_id: number;
  radius_of_curvature: number;
  center_offset: number;
  processing_time_ms: number;
  timestamp: number;
}

export interface FrameMessage {
  type: 'frame';
  jpeg_b64: string;
  telemetry: Telemetry;
}
