import { useEffect, useState } from 'react';
import { wsClient } from '../lib/ws';
import { Telemetry } from '../types';

export default function CurvatureGauge() {
  const [curvature, setCurvature] = useState<number>(0);

  useEffect(() => {
    return wsClient.subscribeToFrames((msg) => {
      setCurvature(msg.telemetry.radius_of_curvature);
    });
  }, []);

  // Geometry for the arc gauge
  const radius = 64;
  const strokeWidth = 12;
  const circumference = 2 * Math.PI * radius;
  // Arc spans 270 degrees (3/4 of a circle)
  const arcSpan = circumference * 0.75;
  const offset = circumference * 0.25; // start from bottom left

  // Map 0-3000m to 0-arcSpan
  const mappedValue = Math.min(Math.max(curvature, 0), 3000);
  const fillPct = mappedValue / 3000;
  const dashOffset = circumference - (arcSpan * fillPct);

  // Color logic based on curvature
  const getColor = () => {
    if (curvature > 1000) return 'stroke-accent-green';
    if (curvature >= 300) return 'stroke-accent-amber';
    return 'stroke-accent-red';
  };

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-radius-card p-6 flex items-center justify-between transition-transform duration-200 hover:-translate-y-1 shadow-[var(--glow-blue)] hover:shadow-lg" id="curvature-gauge">
      <div className="flex flex-col">
        <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-2">Radius of Curvature</h3>
        <div className="flex items-baseline gap-1">
          <span className="font-mono text-4xl font-bold text-text-primary tabular-nums">
            {curvature.toFixed(0)}
          </span>
          <span className="text-text-secondary">m</span>
        </div>
        <p className="text-xs text-text-secondary mt-2">
          {curvature > 1000 ? 'Straight' : curvature > 300 ? 'Gentle Curve' : 'Sharp Curve'}
        </p>
      </div>
      
      <div className="relative w-36 h-36">
        <svg className="w-full h-full -rotate-90 transform" viewBox="0 0 160 160">
          <circle
            cx="80"
            cy="80"
            r={radius}
            fill="none"
            className="stroke-bg-surface-2"
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={circumference - arcSpan}
            strokeLinecap="round"
          />
          <circle
            cx="80"
            cy="80"
            r={radius}
            fill="none"
            className={`${getColor()} transition-all duration-150 ease-out`}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
          />
        </svg>
      </div>
    </div>
  );
}
