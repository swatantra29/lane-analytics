import { useCallback, useEffect, useState } from 'react';
import Header from './components/Header';
import VideoPanel from './components/VideoPanel';
import CurvatureGauge from './components/CurvatureGauge';
import OffsetTicker from './components/OffsetTicker';
import LatencySparkline from './components/LatencySparkline';
import MetricsChart from './components/MetricsChart';
import { wsClient } from './lib/ws';
import { Telemetry } from './types';

export default function App() {
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    wsClient.connect();
    const unsub = wsClient.subscribeToPaused(setPaused);
    return () => {
      unsub();
      wsClient.disconnect();
    };
  }, []);

  const handleTelemetry = useCallback((t: Telemetry) => setTelemetry(t), []);

  const togglePause = () => {
    const next = !paused;
    wsClient.sendControl(next ? 'pause' : 'resume');
    // Optimistic local update; server will confirm via status message
    setPaused(next);
  };

  return (
    <div className="min-h-screen bg-bg-primary text-text-primary flex flex-col font-sans">
      <Header />

      <main className="flex-1 p-4 md:p-6 lg:p-8 max-w-[1600px] mx-auto w-full flex flex-col gap-6">

        {/* Top Grid: Video Panel and Telemetry */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Column A: Video feed + controls */}
          <div className="lg:col-span-2 flex flex-col gap-3">
            <VideoPanel onTelemetry={handleTelemetry} />

            {/* ── HUD bar below video ─────────────────────────────────── */}
            <div
              id="hud-bar"
              className="flex items-center justify-between gap-4 bg-bg-surface rounded-radius-card border border-border-subtle px-5 py-3"
            >
              {/* Curvature */}
              <div className="flex flex-col items-center min-w-[110px]">
                <span className="text-[10px] uppercase tracking-widest text-text-secondary font-semibold mb-0.5">
                  Curvature
                </span>
                <span className="font-mono text-2xl font-bold text-text-primary tabular-nums">
                  {telemetry ? telemetry.radius_of_curvature.toFixed(1) : '—'}
                  <span className="text-sm text-text-secondary ml-1 font-normal">m</span>
                </span>
              </div>

              <div className="h-10 w-px bg-border-subtle" />

              {/* Center Offset */}
              <div className="flex flex-col items-center min-w-[110px]">
                <span className="text-[10px] uppercase tracking-widest text-text-secondary font-semibold mb-0.5">
                  Center Offset
                </span>
                <span className="font-mono text-2xl font-bold text-accent-blue tabular-nums">
                  {telemetry
                    ? (telemetry.center_offset > 0 ? '+' : '') + telemetry.center_offset.toFixed(2)
                    : '—'}
                  <span className="text-sm text-text-secondary ml-1 font-normal">m</span>
                </span>
              </div>

              <div className="h-10 w-px bg-border-subtle" />

              {/* Frame ID */}
              <div className="flex flex-col items-center min-w-[80px]">
                <span className="text-[10px] uppercase tracking-widest text-text-secondary font-semibold mb-0.5">
                  Frame
                </span>
                <span className="font-mono text-xl font-semibold text-text-primary tabular-nums">
                  {telemetry ? telemetry.frame_id : '—'}
                </span>
              </div>

              {/* Spacer */}
              <div className="flex-1" />

              {/* ── Start / Stop button ─────────────────────────────── */}
              <button
                id="pipeline-toggle-btn"
                onClick={togglePause}
                className={`
                  flex items-center gap-2 px-5 py-2.5 rounded-lg font-semibold text-sm
                  border transition-all duration-200 focus:outline-none focus:ring-2
                  focus:ring-offset-2 focus:ring-offset-bg-surface
                  ${paused
                    ? 'bg-accent-green/15 text-accent-green border-accent-green/30 hover:bg-accent-green/25 focus:ring-accent-green'
                    : 'bg-accent-red/15 text-accent-red border-accent-red/30 hover:bg-accent-red/25 focus:ring-accent-red'
                  }
                `}
              >
                {/* Icon */}
                {paused ? (
                  <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M3 2.5l10 5.5-10 5.5V2.5z" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
                    <rect x="3" y="2" width="4" height="12" rx="1" />
                    <rect x="9" y="2" width="4" height="12" rx="1" />
                  </svg>
                )}
                {paused ? 'Resume' : 'Pause'}
              </button>
            </div>
          </div>

          {/* Column B: Telemetry Panel */}
          <div className="flex flex-col gap-6" id="telemetry-panel">
            <CurvatureGauge />
            <OffsetTicker />
            <LatencySparkline />
          </div>

        </div>

        {/* Bottom Section: Chart */}
        <div className="w-full">
          <MetricsChart />
        </div>

      </main>
    </div>
  );
}
