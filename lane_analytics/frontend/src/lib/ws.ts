import { FrameMessage } from '../types';

type FrameListener = (msg: FrameMessage) => void;
type StatusListener = (status: 'connecting' | 'live' | 'disconnected') => void;
type PausedListener = (paused: boolean) => void;

class LaneWSClient {
  private ws: WebSocket | null = null;
  private url: string;
  public status: 'connecting' | 'live' | 'disconnected' = 'disconnected';
  public paused: boolean = false;
  private frameListeners: Set<FrameListener> = new Set();
  private statusListeners: Set<StatusListener> = new Set();
  private pausedListeners: Set<PausedListener> = new Set();
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private retryCount: number = 0;

  constructor(url: string) {
    this.url = url;
  }

  public connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    this.updateStatus('connecting');

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.updateStatus('live');
        this.retryCount = 0;
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'frame') {
            this.frameListeners.forEach((l) => l(data as FrameMessage));
          } else if (data.type === 'status' && typeof data.paused === 'boolean') {
            this.paused = data.paused;
            this.pausedListeners.forEach((l) => l(this.paused));
          }
        } catch (err) {
          console.error('Failed to parse WS message:', err);
        }
      };

      this.ws.onclose = () => {
        this.updateStatus('disconnected');
        this.scheduleReconnect();
      };

      this.ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        this.ws?.close();
      };
    } catch (err) {
      console.error('Failed to create WebSocket:', err);
      this.updateStatus('disconnected');
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout);
    const delay = Math.min(1000 * Math.pow(2, this.retryCount), 30000);
    this.retryCount++;
    this.reconnectTimeout = setTimeout(() => this.connect(), delay);
  }

  public disconnect() {
    if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout);
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.updateStatus('disconnected');
  }

  /** Send a control message to the backend (pause / resume). */
  public sendControl(action: 'pause' | 'resume') {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'control', action }));
    }
  }

  private updateStatus(newStatus: 'connecting' | 'live' | 'disconnected') {
    if (this.status !== newStatus) {
      this.status = newStatus;
      this.statusListeners.forEach((l) => l(newStatus));
      document.dispatchEvent(
        new CustomEvent('ws-status-change', { detail: { status: newStatus } })
      );
    }
  }

  public subscribeToFrames(listener: FrameListener) {
    this.frameListeners.add(listener);
    return () => this.frameListeners.delete(listener);
  }

  public subscribeToStatus(listener: StatusListener) {
    this.statusListeners.add(listener);
    listener(this.status);
    return () => this.statusListeners.delete(listener);
  }

  public subscribeToPaused(listener: PausedListener) {
    this.pausedListeners.add(listener);
    listener(this.paused);
    return () => this.pausedListeners.delete(listener);
  }
}

export const wsClient = new LaneWSClient('ws://localhost:8765');
