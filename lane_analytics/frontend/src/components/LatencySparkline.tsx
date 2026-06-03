import { useEffect, useRef, useState } from 'react';
import { wsClient } from '../lib/ws';

export default function LatencySparkline() {
  const [latency, setLatency] = useState<number>(0);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const historyRef = useRef<number[]>(Array(60).fill(0));

  useEffect(() => {
    return wsClient.subscribeToFrames((msg) => {
      const val = msg.telemetry.processing_time_ms;
      setLatency(val);
      
      const history = historyRef.current;
      history.shift();
      history.push(val);
      
      drawSparkline();
    });
  }, []);

  const drawSparkline = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    
    ctx.clearRect(0, 0, width, height);
    
    const history = historyRef.current;
    const maxVal = Math.max(...history, 50); // Minimum scale of 50ms
    
    ctx.beginPath();
    ctx.strokeStyle = '#4dabf7'; // accent-blue
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    const step = width / (history.length - 1);

    for (let i = 0; i < history.length; i++) {
      const x = i * step;
      // Invert Y mapping
      const y = height - ((history[i] / maxVal) * height * 0.8) - 2; 
      
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Fill under line
    ctx.lineTo(width, height);
    ctx.lineTo(0, height);
    ctx.closePath();
    
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, '#4dabf740'); // semi-transparent blue
    gradient.addColorStop(1, '#4dabf700'); 
    ctx.fillStyle = gradient;
    ctx.fill();
  };

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-radius-card p-6 flex flex-col justify-between transition-transform duration-200 hover:-translate-y-1 hover:shadow-lg" id="latency-card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wider">Processing Latency</h3>
        <div className="font-mono text-2xl font-bold text-text-primary tabular-nums">
          {latency.toFixed(1)} <span className="text-sm text-text-secondary font-sans font-normal">ms</span>
        </div>
      </div>
      <div className="h-16 w-full relative">
        <canvas 
          ref={canvasRef} 
          width={280} 
          height={64}
          className="w-full h-full"
        />
      </div>
    </div>
  );
}
