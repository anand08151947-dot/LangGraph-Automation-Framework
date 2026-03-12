
import React, { useEffect, useState } from 'react';
import { Card } from '../components/Shared';
import { getSystemHealth } from '../services/api';

const HelpView: React.FC = () => {
  const [health, setHealth] = useState<any>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  useEffect(() => {
    getSystemHealth()
      .then(setHealth)
      .catch((e: any) => setHealthError(e?.message || 'Unable to reach backend'));
  }, []);

  const isHealthy = health && (health.status === 'ok' || health.status === 'healthy');

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in duration-500">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold text-slate-800">Documentation & Resources</h1>
        <p className="text-slate-500">Master the Agentic AI Workbench with our guides and examples.</p>
      </div>

      {/* System Status */}
      <Card title="System Status">
        {healthError ? (
          <div className="flex items-center gap-3 p-3 bg-rose-50 border border-rose-200 rounded-xl">
            <div className="w-3 h-3 rounded-full bg-rose-500"></div>
            <p className="text-sm font-medium text-rose-700">Backend unreachable: {healthError}</p>
          </div>
        ) : health ? (
          <div className="flex items-center gap-4 p-3 bg-emerald-50 border border-emerald-200 rounded-xl">
            <div className="w-3 h-3 rounded-full bg-emerald-500"></div>
            <div>
              <p className="text-sm font-bold text-emerald-700">System {isHealthy ? 'Healthy' : 'Degraded'}</p>
              {health.version && <p className="text-xs text-slate-500">Version: {health.version}</p>}
              {health.status && <p className="text-xs text-slate-500">Status: {health.status}</p>}
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-xl">
            <div className="w-3 h-3 rounded-full bg-slate-300 animate-pulse"></div>
            <p className="text-sm text-slate-500">Checking backend health...</p>
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card title="Getting Started" className="hover:border-indigo-300 transition-colors">
          <ul className="space-y-4">
            {['Creating your first agent', 'Understanding workflows', 'Connecting to MCP servers', 'Defining tool schemas'].map((item, i) => (
              <li key={i} className="flex items-center gap-3 group cursor-pointer">
                <i className="fas fa-chevron-right text-xs text-slate-300 group-hover:text-indigo-500 transition-colors"></i>
                <span className="text-slate-600 group-hover:text-slate-900 font-medium">{item}</span>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Core Concepts" className="hover:border-indigo-300 transition-colors">
          <ul className="space-y-4">
            {['Agent-to-Agent communication', 'Routing & Logic steps', 'State management', 'Error handling patterns'].map((item, i) => (
              <li key={i} className="flex items-center gap-3 group cursor-pointer">
                <i className="fas fa-book-open text-xs text-slate-300 group-hover:text-indigo-500 transition-colors"></i>
                <span className="text-slate-600 group-hover:text-slate-900 font-medium">{item}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card title="API Reference">
        <div className="space-y-4">
          <div className="p-4 bg-slate-50 rounded-lg font-mono text-sm border border-slate-100">
            <p className="text-emerald-600 font-bold mb-1">POST /orchestrate_async</p>
            <p className="text-slate-500">Starts a new asynchronous workflow execution using a provided JSON config.</p>
          </div>
          <div className="p-4 bg-slate-50 rounded-lg font-mono text-sm border border-slate-100">
            <p className="text-blue-600 font-bold mb-1">GET /status/{"{run_id}"}</p>
            <p className="text-slate-500">Polls the current status and retrieves execution logs for a specific run.</p>
          </div>
          <div className="p-4 bg-slate-50 rounded-lg font-mono text-sm border border-slate-100">
            <p className="text-amber-600 font-bold mb-1">POST /english_to_json</p>
            <p className="text-slate-500">Translates human-readable instructions into a valid workbench JSON schema.</p>
          </div>
        </div>
      </Card>

      <div className="bg-indigo-50 p-8 rounded-2xl flex flex-col items-center text-center space-y-4">
        <div className="w-16 h-16 bg-white rounded-2xl shadow-sm flex items-center justify-center text-indigo-600 text-2xl">
          <i className="fas fa-users"></i>
        </div>
        <h3 className="text-xl font-bold text-slate-800">Join the Community</h3>
        <p className="text-slate-500 max-w-md">Connect with other developers building advanced agentic systems. Share templates and best practices on our Discord.</p>
        <button className="px-8 py-3 bg-indigo-600 text-white rounded-xl font-bold shadow-lg shadow-indigo-200 hover:bg-indigo-700 active:scale-95 transition-all">
          Join Discord Server
        </button>
      </div>
    </div>
  );
};

export default HelpView;
