import { useEffect, useRef } from 'react';
import { wsClient } from '../lib/ws';

const BUFFER_SIZE = 300;

export default function MetricsChart() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  
  // Rolling buffers
  const dataRef = useRef({
    frames: new Float32Array(BUFFER_SIZE),
    curvature: new Float32Array(BUFFER_SIZE),
    offset: new Float32Array(BUFFER_SIZE),
    head: 0,
    count: 0
  });

  useEffect(() => {
    return wsClient.subscribeToFrames((msg) => {
      const data = dataRef.current;
      const idx = data.head;
      
      data.frames[idx] = msg.telemetry.frame_id;
      data.curvature[idx] = msg.telemetry.radius_of_curvature;
      data.offset[idx] = msg.telemetry.center_offset;
      
      data.head = (idx + 1) % BUFFER_SIZE;
      if (data.count < BUFFER_SIZE) data.count++;
    });
  }, []);

  useEffect(() => {
    let animationFrameId: number;

    const renderLoop = () => {
      drawChart();
      animationFrameId = requestAnimationFrame(renderLoop);
    };

    renderLoop();
    return () => cancelAnimationFrame(animationFrameId);
  }, []);

  const drawChart = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Handle high DPI displays
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    
    // Only resize if needed to prevent constant clearing
    if (canvas.width !== rect.width * dpr || canvas.height !== rect.height * dpr) {
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
    }
    
    const width = rect.width;
    const height = rect.height;

    // Margins for axes
    const padL = 60, padR = 60, padT = 30, padB = 30;
    const chartW = width - padL - padR;
    const chartH = height - padT - padB;

    // Clear
    ctx.clearRect(0, 0, width, height);

    // Background
    ctx.fillStyle = '#0f0f18'; // bg-surface
    ctx.fillRect(padL, padT, chartW, chartH);

    // Grid lines (horizontal)
    ctx.strokeStyle = '#ffffff0d';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i <= 5; i++) {
      const y = padT + (chartH * i) / 5;
      ctx.moveTo(padL, y);
      ctx.lineTo(width - padR, y);
    }
    ctx.stroke();

    const data = dataRef.current;
    if (data.count === 0) return; // nothing to draw

    // Helper to traverse buffer in chronological order
    const getPoint = (i: number) => {
      const idx = data.count < BUFFER_SIZE 
        ? i 
        : (data.head + i) % BUFFER_SIZE;
      return {
        frame: data.frames[idx],
        curv: data.curvature[idx],
        off: data.offset[idx]
      };
    };

    // Draw Curvature (Left Y-axis: 0 - 3000)
    ctx.beginPath();
    ctx.strokeStyle = '#4dabf7'; // accent-blue
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    
    for (let i = 0; i < data.count; i++) {
      const pt = getPoint(i);
      const x = padL + (i / (BUFFER_SIZE - 1)) * chartW;
      const clampedCurv = Math.min(Math.max(pt.curv, 0), 3000);
      const y = padT + chartH - (clampedCurv / 3000) * chartH;
      
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Draw Offset (Right Y-axis: -1.5 to 1.5)
    ctx.beginPath();
    ctx.strokeStyle = '#ff9f40'; // accent-orange
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    
    for (let i = 0; i < data.count; i++) {
      const pt = getPoint(i);
      const x = padL + (i / (BUFFER_SIZE - 1)) * chartW;
      const clampedOff = Math.min(Math.max(pt.off, -1.5), 1.5);
      // Map -1.5..1.5 to H..0
      const normOff = (clampedOff + 1.5) / 3.0;
      const y = padT + chartH - normOff * chartH;
      
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Axes styling
    ctx.fillStyle = '#7c7f93'; // text-secondary
    ctx.font = '10px Inter, sans-serif';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';

    // Left Y Axis (Curvature)
    for (let i = 0; i <= 3; i++) {
      const val = 3000 - i * 1000;
      const y = padT + (chartH * i) / 3;
      ctx.fillText(val + 'm', padL - 10, y);
    }

    // Right Y Axis (Offset)
    ctx.textAlign = 'left';
    for (let i = 0; i <= 4; i++) {
      const val = (1.5 - i * 0.75).toFixed(2);
      const y = padT + (chartH * i) / 4;
      ctx.fillText((parseFloat(val) > 0 ? '+' : '') + val, width - padR + 10, y);
    }

    // X Axis (Frames) - label every 50 frames roughly
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    const numLabels = 6;
    for (let i = 0; i < numLabels; i++) {
      const pointIdx = Math.floor(i * (data.count - 1) / (numLabels - 1));
      if (pointIdx >= 0 && pointIdx < data.count) {
        const pt = getPoint(pointIdx);
        const x = padL + (pointIdx / (BUFFER_SIZE - 1)) * chartW;
        ctx.fillText(pt.frame.toString(), x, height - padB + 10);
      }
    }

    // Legend
    ctx.textAlign = 'right';
    ctx.textBaseline = 'top';
    
    // Curvature Legend
    ctx.fillStyle = '#4dabf7';
    ctx.fillRect(width - padR - 150, padT - 20, 10, 10);
    ctx.fillStyle = '#e8eaf0';
    ctx.fillText('Curvature (m)', width - padR - 70, padT - 20);

    // Offset Legend
    ctx.fillStyle = '#ff9f40';
    ctx.fillRect(width - padR - 60, padT - 20, 10, 10);
    ctx.fillStyle = '#e8eaf0';
    ctx.fillText('Offset (m)', width - padR, padT - 20);
  };

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-radius-card p-4 relative" id="metrics-chart">
      <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-2 px-2">Live Metrics History</h3>
      <div className="w-full h-[300px]">
        <canvas
          id="metricsChart"
          ref={canvasRef}
          className="w-full h-full block"
        />
      </div>
    </div>
  );
}
