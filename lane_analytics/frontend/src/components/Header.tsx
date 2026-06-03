import { useEffect, useState } from 'react';
import { wsClient } from '../lib/ws';
import { Activity } from 'lucide-react';

export default function Header() {
  const [status, setStatus] = useState<'connecting' | 'live' | 'disconnected'>('disconnected');

  useEffect(() => {
    return wsClient.subscribeToStatus(setStatus);
  }, []);

  const getStatusStyles = () => {
    switch (status) {
      case 'live':
        return 'bg-accent-green/20 text-accent-green border-accent-green/30 animate-pulse';
      case 'connecting':
        return 'bg-accent-amber/20 text-accent-amber border-accent-amber/30';
      case 'disconnected':
      default:
        return 'bg-accent-red/20 text-accent-red border-accent-red/30';
    }
  };

  return (
    <header className="flex items-center justify-between px-6 py-4 border-b border-border-subtle bg-bg-surface/80 backdrop-blur-md sticky top-0 z-10" id="header">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-accent-blue/10 rounded-lg border border-accent-blue/20">
          <Activity className="w-5 h-5 text-accent-blue" />
        </div>
        <h1 className="text-xl font-semibold tracking-tight text-text-primary">
          Lane Analytics
        </h1>
      </div>
      
      <div className={`px-3 py-1 rounded-full border text-xs font-semibold tracking-wide uppercase transition-colors duration-300 ${getStatusStyles()}`} id="status-pill">
        {status}
      </div>
    </header>
  );
}
