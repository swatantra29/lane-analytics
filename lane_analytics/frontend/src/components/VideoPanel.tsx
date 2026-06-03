import { useEffect, useRef } from 'react';
import { wsClient } from '../lib/ws';
import { Telemetry } from '../types';

interface VideoPanelProps {
  onTelemetry: (t: Telemetry) => void;
}

export default function VideoPanel({ onTelemetry }: VideoPanelProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    return wsClient.subscribeToFrames((msg) => {
      onTelemetry(msg.telemetry);

      if (!canvasRef.current) return;
      const canvas = canvasRef.current;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const img = new Image();
      img.onload = () => {
        ctx.fillStyle = '#0a0a0f';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        const canvasRatio = canvas.width / canvas.height;
        const imgRatio = img.width / img.height;

        let drawWidth, drawHeight, offsetX = 0, offsetY = 0;
        if (imgRatio > canvasRatio) {
          drawWidth = canvas.width;
          drawHeight = canvas.width / imgRatio;
          offsetY = (canvas.height - drawHeight) / 2;
        } else {
          drawHeight = canvas.height;
          drawWidth = canvas.height * imgRatio;
          offsetX = (canvas.width - drawWidth) / 2;
        }

        ctx.drawImage(img, offsetX, offsetY, drawWidth, drawHeight);
      };
      img.src = `data:image/jpeg;base64,${msg.jpeg_b64}`;
    });
  }, [onTelemetry]);

  // Keep canvas resolution in sync with its container
  useEffect(() => {
    const handleResize = () => {
      if (canvasRef.current) {
        const parent = canvasRef.current.parentElement;
        if (parent) {
          canvasRef.current.width = parent.clientWidth;
          canvasRef.current.height = parent.clientHeight;
        }
      }
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return (
    <div
      className="relative w-full h-[300px] lg:h-[520px] bg-bg-surface-2 rounded-radius-card overflow-hidden border border-border-subtle"
      id="video-panel"
    >
      <canvas id="videoCanvas" ref={canvasRef} className="w-full h-full" />
    </div>
  );
}
