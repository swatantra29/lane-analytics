import { useEffect, useState } from 'react';
import { wsClient } from '../lib/ws';

export default function OffsetTicker() {
  const [offset, setOffset] = useState<number>(0);

  useEffect(() => {
    return wsClient.subscribeToFrames((msg) => {
      setOffset(msg.telemetry.center_offset);
    });
  }, []);

  const getColor = (val: number) => {
    const abs = Math.abs(val);
    if (abs < 0.3) return 'bg-accent-green';
    if (abs < 0.6) return 'bg-accent-amber';
    return 'bg-accent-red';
  };

  // Map -1.5 to +1.5 to 0-100%
  const clamp = (val: number, min: number, max: number) => Math.min(Math.max(val, min), max);
  const percent = ((clamp(offset, -1.5, 1.5) + 1.5) / 3.0) * 100;

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-radius-card p-6 flex flex-col justify-between transition-transform duration-200 hover:-translate-y-1 hover:shadow-lg" id="offset-ticker">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wider">Center Offset</h3>
        <div className="font-mono text-2xl font-bold tabular-nums">
          <span className={Math.abs(offset) >= 0.6 ? 'text-accent-red' : 'text-text-primary'}>
            {offset > 0 ? '+' : ''}{offset.toFixed(2)}
          </span>
          <span className="text-sm text-text-secondary font-sans font-normal ml-1">m</span>
        </div>
      </div>
      
      <div className="relative w-full h-3 bg-bg-surface-2 rounded-full overflow-hidden">
        {/* Center mark */}
        <div className="absolute top-0 bottom-0 left-1/2 w-0.5 -ml-px bg-border-subtle z-10"></div>
        {/* Indicator dot */}
        <div 
          className={`absolute top-0 bottom-0 w-4 h-4 -mt-0.5 rounded-full shadow-md transition-all duration-150 ease-out ${getColor(offset)}`}
          style={{ left: `calc(${percent}% - 8px)` }}
        />
        {/* Track fill from center */}
        <div 
          className={`absolute top-0 bottom-0 opacity-40 transition-all duration-150 ease-out ${getColor(offset)}`}
          style={{ 
            left: offset < 0 ? `${percent}%` : '50%',
            right: offset < 0 ? '50%' : `${100 - percent}%`
          }}
        />
      </div>
      
      <div className="flex justify-between text-xs text-text-secondary mt-2 font-mono">
        <span>-1.5m</span>
        <span>0</span>
        <span>+1.5m</span>
      </div>
    </div>
  );
}
