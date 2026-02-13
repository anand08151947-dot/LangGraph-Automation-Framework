

import React, { useEffect } from 'react';
import { Card, Badge, Button } from '../components/Shared';
import { WorkflowStatus } from '../types';
import { useMonitorRuns } from '../hooks/useMonitorRuns';


const MonitorView: React.FC = () => {
  const { runs, selectedRun, loading, error, loadRuns, selectRun } = useMonitorRuns();

  useEffect(() => {
    loadRuns();
  }, []);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 animate-in fade-in duration-500">
      <div className="lg:col-span-1 space-y-6">
        <Card title="Active & Recent Runs">
          <div className="space-y-4">
            {loading ? (
              <div className="p-4 text-center text-slate-400">Loading runs...</div>
            ) : error ? (
              <div className="p-4 text-center text-rose-400">{error}</div>
            ) : runs.length === 0 ? (
              <div className="p-4 text-center text-slate-400">No runs available.</div>
            ) : (
              runs.map(run => (
                <button
                  key={run.id}
                  onClick={() => selectRun(run.id)}
                  className={`w-full p-4 rounded-xl border text-left transition-all ${
                    selectedRun && selectedRun.id === run.id ? 'border-indigo-500 bg-indigo-50 ring-1 ring-indigo-500' : 'border-slate-100 bg-white hover:border-slate-300'
                  }`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <h4 className="font-bold text-slate-800">{run.name}</h4>
                    <Badge type={run.status} label={run.status} />
                  </div>
                  <div className="flex justify-between text-xs text-slate-500 font-medium">
                    <span>ID: {run.id}</span>
                    <span>{run.startTime}</span>
                  </div>
                </button>
              ))
            )}
          </div>
        </Card>
      </div>

      <div className="lg:col-span-2 space-y-6">
        <Card>
          {selectedRun ? (
            <>
              <div className="flex justify-between items-center mb-6">
                <div>
                  <h2 className="text-xl font-bold text-slate-800">{selectedRun.name}</h2>
                  <p className="text-sm text-slate-500">Run ID: <span className="font-mono">{selectedRun.id}</span></p>
                </div>
                <div className="flex gap-2">
                  <Button variant="secondary" className="text-sm"><i className="fas fa-redo mr-2"></i> Rerun</Button>
                  <Button variant="danger" className="text-sm"><i className="fas fa-stop mr-2"></i> Stop</Button>
                </div>
              </div>

              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Duration</p>
                    <p className="text-xl font-bold text-slate-800">{selectedRun.duration || '--'}</p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Memory Use</p>
                    <p className="text-xl font-bold text-slate-800">{selectedRun.memory || '--'}</p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Success Rate</p>
                    <p className="text-xl font-bold text-slate-800">{selectedRun.successRate || '--'}</p>
                  </div>
                </div>

                <div className="space-y-2">
                  <h3 className="font-bold text-slate-800">Execution Logs</h3>
                  <div className="bg-slate-900 rounded-xl p-6 font-mono text-sm h-80 overflow-y-auto space-y-2">
                    {selectedRun.logs && selectedRun.logs.length > 0 ? (
                      selectedRun.logs.map((log, i) => (
                        <div key={i} className="flex gap-4">
                          <span className="text-slate-500">[{new Date().toLocaleTimeString()}]</span>
                          <span className={log.includes('Failed') ? 'text-rose-400' : 'text-emerald-400'}>
                            {log.includes('Initialized') ? '●' : '○'} {log}
                          </span>
                        </div>
                      ))
                    ) : (
                      <div className="text-slate-400">No logs available.</div>
                    )}
                    {selectedRun.status === WorkflowStatus.RUNNING && (
                      <div className="flex gap-4 animate-pulse">
                        <span className="text-slate-500">[{new Date().toLocaleTimeString()}]</span>
                        <span className="text-indigo-400">Processing next step...</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="p-4 text-center text-slate-400">Select a run to view details.</div>
          )}
        </Card>
      </div>
    </div>
  );
};

export default MonitorView;
