
import React, { useEffect, useRef, useState } from 'react';
import { Card, Badge, Button } from '../components/Shared';
import { WorkflowStatus } from '../types';
import { useMonitorRuns } from '../hooks/useMonitorRuns';
import { getRunConfig, getStm, getLtm, getApprovalStatus, submitApproval } from '../services/api.runs';
import { RunItemSkeleton } from '../components/Skeleton';
import { ErrorBoundary } from '../components/ErrorBoundary';

const WS_BASE = ((import.meta as any).env?.VITE_API_BASE || 'http://localhost:8000')
  .replace(/^http/, 'ws');

type Tab = 'logs' | 'config' | 'memory';

const MonitorView: React.FC = () => {
  const { runs, selectedRun, loading, error, actionLoading, loadRuns, selectRun, cancelRun, rerunRun } = useMonitorRuns();
  const [activeTab, setActiveTab] = useState<Tab>('logs');
  const [runConfig, setRunConfig] = useState<any>(null);
  const [stm, setStm] = useState<any>(null);
  const [ltm, setLtm] = useState<any[]>([]);
  const [liveLog, setLiveLog] = useState<string[]>([]);
  const [logSearch, setLogSearch] = useState('');
  // FE-MON-2: Approval state
  const [approvalInfo, setApprovalInfo] = useState<{ checkpoint_node?: string; state_snapshot?: any } | null>(null);
  const [approvalInput, setApprovalInput] = useState('{}');
  const [approvalSubmitting, setApprovalSubmitting] = useState(false);
  const [approvalError, setApprovalError] = useState('');
  const wsRef = useRef<WebSocket | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadRuns();
  }, []);

  // FE-MON-3: WebSocket live log streaming
  useEffect(() => {
    if (!selectedRun) return;

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setLiveLog([]);

    const isActive = [WorkflowStatus.running, WorkflowStatus.started, WorkflowStatus.RUNNING, WorkflowStatus.PENDING]
      .map(s => s as string).includes(selectedRun.status as string);

    if (!isActive) return;

    const ws = new WebSocket(`${WS_BASE}/ws/status/${selectedRun.id}`);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        const status = data.status || '';
        const msg = `[${new Date().toLocaleTimeString()}] Status: ${status}` +
          (data.result ? ` — ${typeof data.result === 'string' ? data.result : JSON.stringify(data.result)}` : '');
        setLiveLog(prev => [...prev, msg]);
        if (['completed', 'failed', 'cancelled', 'error'].includes(status)) {
          loadRuns();
          ws.close();
        }
      } catch { /* ignore parse errors */ }
    };
    ws.onerror = () => setLiveLog(prev => [...prev, `[${new Date().toLocaleTimeString()}] WebSocket error`]);

    return () => { ws.close(); };
  }, [selectedRun?.id]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [liveLog, selectedRun?.logs]);

  // FE-MON-6: Load run config when Config tab selected
  useEffect(() => {
    if (activeTab === 'config' && selectedRun) {
      getRunConfig(selectedRun.id)
        .then(d => setRunConfig(d))
        .catch(() => setRunConfig(null));
    }
  }, [activeTab, selectedRun?.id]);

  // MEM-6: Load STM/LTM when Memory tab selected
  useEffect(() => {
    if (activeTab === 'memory' && selectedRun) {
      getStm(selectedRun.id).then(d => setStm(d?.stm ?? null)).catch(() => setStm(null));
      getLtm(selectedRun.id).then(d => setLtm(d?.ltm ?? [])).catch(() => setLtm([]));
    }
  }, [activeTab, selectedRun?.id]);

  // FE-MON-2: Fetch approval info when status is awaiting_approval
  useEffect(() => {
    if (!selectedRun) return;
    const status = (selectedRun.status as string).toLowerCase();
    if (status === 'awaiting_approval') {
      getApprovalStatus(selectedRun.id)
        .then(d => { setApprovalInfo(d); setApprovalError(''); })
        .catch(() => setApprovalInfo(null));
    } else {
      setApprovalInfo(null);
    }
  }, [selectedRun?.id, selectedRun?.status]);

  const handleApprovalSubmit = async () => {
    if (!selectedRun) return;
    let parsed: any;
    try { parsed = JSON.parse(approvalInput); } catch { setApprovalError('Invalid JSON'); return; }
    setApprovalSubmitting(true);
    setApprovalError('');
    try {
      await submitApproval(selectedRun.id, parsed);
      loadRuns();
      setApprovalInfo(null);
    } catch (e: any) {
      setApprovalError(e?.response?.data?.detail ?? 'Approval submission failed');
    }
    setApprovalSubmitting(false);
  };

  const allLogs = [...(selectedRun?.logs || []), ...liveLog];
  // FE-MON-5: Filter logs by search term
  const displayLogs = logSearch.trim()
    ? allLogs.filter(l => l.toLowerCase().includes(logSearch.toLowerCase()))
    : allLogs;

  // FE-MON-5: Download logs as .txt
  const downloadLogs = () => {
    const blob = new Blob([allLogs.join('\n')], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `run-${selectedRun?.id?.slice(0, 8) ?? 'logs'}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const isActive = (status: string) =>
    ['running', 'started', 'RUNNING', 'PENDING'].includes(status);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 animate-in fade-in duration-500">
      <div className="lg:col-span-1 space-y-6">
        <Card title="Active & Recent Runs">
          <div className="space-y-4">
            {loading ? (
              Array.from({ length: 3 }).map((_, i) => <RunItemSkeleton key={i} />)
            ) : error ? (
              <div className="p-4 text-center text-rose-400">{error}</div>
            ) : runs.length === 0 ? (
              <div className="p-4 text-center text-slate-400">No runs available.</div>
            ) : (
              runs.map(run => (
                <button
                  key={run.id}
                  onClick={() => { selectRun(run.id); setActiveTab('logs'); }}
                  className={`w-full p-4 rounded-xl border text-left transition-all ${
                    selectedRun && selectedRun.id === run.id ? 'border-indigo-500 bg-indigo-50 ring-1 ring-indigo-500' : 'border-slate-100 bg-white hover:border-slate-300'
                  }`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <h4 className="font-bold text-slate-800 truncate max-w-[60%]">{run.name}</h4>
                    <Badge type={run.status} label={run.status} />
                  </div>
                  <div className="flex justify-between text-xs text-slate-500 font-medium">
                    <span className="font-mono truncate max-w-[55%]">{run.id.slice(0, 8)}…</span>
                    <span>{run.startTime}</span>
                  </div>
                </button>
              ))
            )}
          </div>
        </Card>
      </div>

      <div className="lg:col-span-2 space-y-6">
        <ErrorBoundary>
          <Card>
            {selectedRun ? (
              <>
                <div className="flex justify-between items-center mb-4">
                  <div>
                    <h2 className="text-xl font-bold text-slate-800">{selectedRun.name}</h2>
                    <p className="text-sm text-slate-500">Run ID: <span className="font-mono">{selectedRun.id}</span></p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      className="text-sm"
                      disabled={actionLoading}
                      onClick={async () => {
                        let cfg = selectedRun.config;
                        if (!cfg) {
                          try { cfg = (await getRunConfig(selectedRun.id)).config; } catch { cfg = null; }
                        }
                        if (cfg) rerunRun(cfg);
                      }}
                    >
                      <i className="fas fa-redo mr-2"></i> Rerun
                    </Button>
                    <Button
                      variant="danger"
                      className="text-sm"
                      disabled={actionLoading || !isActive(selectedRun.status as string)}
                      onClick={() => cancelRun(selectedRun.id)}
                    >
                      <i className="fas fa-stop mr-2"></i> Stop
                    </Button>
                  </div>
                </div>

                {/* FE-MON-2: Human-in-loop approval panel */}
                {(selectedRun.status as string).toLowerCase() === 'awaiting_approval' && (
                  <div className="mb-4 p-4 rounded-xl bg-amber-50 border border-amber-200">
                    <div className="flex items-center gap-2 mb-2">
                      <i className="fas fa-hand-paper text-amber-500"></i>
                      <h4 className="font-bold text-amber-800">Human Approval Required</h4>
                    </div>
                    {approvalInfo?.checkpoint_node && (
                      <p className="text-sm text-amber-700 mb-2">
                        Checkpoint: <span className="font-mono font-semibold">{approvalInfo.checkpoint_node}</span>
                      </p>
                    )}
                    {approvalInfo?.state_snapshot && (
                      <pre className="mb-3 p-2 bg-amber-100 text-amber-900 text-xs rounded overflow-auto max-h-24 font-mono">
                        {JSON.stringify(approvalInfo.state_snapshot, null, 2)}
                      </pre>
                    )}
                    <label className="block text-xs font-semibold text-amber-700 mb-1">
                      Approval Input (JSON)
                    </label>
                    <textarea
                      className="w-full font-mono text-xs p-2 border border-amber-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 mb-2"
                      rows={3}
                      value={approvalInput}
                      onChange={e => setApprovalInput(e.target.value)}
                    />
                    {approvalError && <p className="text-xs text-rose-600 mb-2">{approvalError}</p>}
                    <div className="flex gap-2">
                      <Button
                        variant="primary"
                        className="text-sm"
                        disabled={approvalSubmitting}
                        onClick={handleApprovalSubmit}
                      >
                        <i className="fas fa-check mr-1.5"></i>
                        {approvalSubmitting ? 'Submitting…' : 'Submit Approval'}
                      </Button>
                      <Button
                        variant="danger"
                        className="text-sm"
                        disabled={approvalSubmitting}
                        onClick={() => submitApproval(selectedRun.id, { _reject: true }).then(() => { loadRuns(); setApprovalInfo(null); }).catch(() => {})}
                      >
                        <i className="fas fa-times mr-1.5"></i> Reject
                      </Button>
                    </div>
                  </div>
                )}

                {/* Tabs: Logs | Config | Memory */}
                <div className="flex gap-1 mb-4 border-b border-slate-100">
                  {(['logs', 'config', 'memory'] as Tab[]).map(tab => (
                    <button
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      className={`px-4 py-2 text-sm font-semibold capitalize rounded-t transition-colors ${
                        activeTab === tab
                          ? 'text-indigo-600 border-b-2 border-indigo-500 bg-indigo-50'
                          : 'text-slate-500 hover:text-slate-700'
                      }`}
                    >
                      {tab === 'logs' && <i className="fas fa-terminal mr-1.5"></i>}
                      {tab === 'config' && <i className="fas fa-code mr-1.5"></i>}
                      {tab === 'memory' && <i className="fas fa-brain mr-1.5"></i>}
                      {tab.charAt(0).toUpperCase() + tab.slice(1)}
                    </button>
                  ))}
                </div>

                {/* Tab: Logs */}
                {activeTab === 'logs' && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-3 gap-4">
                      <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Duration</p>
                        <p className="text-xl font-bold text-slate-800">{selectedRun.duration || '--'}</p>
                      </div>
                      <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Status</p>
                        <p className="text-xl font-bold text-slate-800 capitalize">{selectedRun.status}</p>
                      </div>
                      <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Success Rate</p>
                        <p className="text-xl font-bold text-slate-800">{selectedRun.successRate || '--'}</p>
                      </div>
                    </div>

                    {/* FE-MON-5: Log search + download */}
                    <div className="flex gap-2 items-center">
                      <div className="relative flex-1">
                        <i className="fas fa-search absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-xs"></i>
                        <input
                          type="text"
                          placeholder="Filter logs…"
                          className="w-full pl-8 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300"
                          value={logSearch}
                          onChange={e => setLogSearch(e.target.value)}
                        />
                      </div>
                      <Button variant="ghost" className="text-xs shrink-0" onClick={downloadLogs} disabled={allLogs.length === 0}>
                        <i className="fas fa-download mr-1.5"></i> Download
                      </Button>
                    </div>

                    <div className="bg-slate-900 rounded-xl p-6 font-mono text-sm h-64 overflow-y-auto space-y-2">
                      {displayLogs.length > 0 ? (
                        displayLogs.map((log, i) => (
                          <div key={i} className="flex gap-4">
                            <span className={log.includes('Failed') || log.includes('error') ? 'text-rose-400' : 'text-emerald-400'}>
                              {log}
                            </span>
                          </div>
                        ))
                      ) : (
                        <div className="text-slate-400">{logSearch ? 'No matching log entries.' : 'No logs available.'}</div>
                      )}
                      {isActive(selectedRun.status as string) && (
                        <div className="flex gap-4 animate-pulse">
                          <span className="text-indigo-400">● Processing…</span>
                        </div>
                      )}
                      <div ref={logEndRef} />
                    </div>
                  </div>
                )}

                {/* Tab: Config (FE-MON-6) */}
                {activeTab === 'config' && (
                  <div className="space-y-2">
                    {runConfig ? (
                      <>
                        {runConfig.template && (
                          <p className="text-xs text-slate-500 mb-2">Template: <span className="font-mono font-semibold">{runConfig.template}</span></p>
                        )}
                        <pre className="bg-slate-900 text-emerald-300 rounded-xl p-4 text-xs overflow-auto h-80 font-mono">
                          {JSON.stringify(runConfig.config, null, 2)}
                        </pre>
                      </>
                    ) : (
                      <div className="text-slate-400 p-4 text-center">No config stored for this run.</div>
                    )}
                  </div>
                )}

                {/* Tab: Memory (MEM-6) */}
                {activeTab === 'memory' && (
                  <div className="space-y-4">
                    <div>
                      <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">Short-Term Memory (STM)</h4>
                      {stm ? (
                        <pre className="bg-slate-900 text-sky-300 rounded-xl p-4 text-xs overflow-auto max-h-40 font-mono">
                          {JSON.stringify(stm, null, 2)}
                        </pre>
                      ) : (
                        <div className="text-slate-400 text-sm">No STM data.</div>
                      )}
                    </div>
                    <div>
                      <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">Long-Term Memory (LTM) — {ltm.length} entries</h4>
                      {ltm.length > 0 ? (
                        <div className="bg-slate-900 rounded-xl p-4 text-xs overflow-auto max-h-48 font-mono space-y-2">
                          {ltm.map((entry, i) => (
                            <div key={i} className="text-amber-300 border-b border-slate-700 pb-2 last:border-0">
                              <span className="text-slate-500">#{i + 1} step {entry.step_idx ?? i}</span>{' '}
                              {JSON.stringify(entry)}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-slate-400 text-sm">No LTM data.</div>
                      )}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="p-4 text-center text-slate-400">Select a run to view details.</div>
            )}
          </Card>
        </ErrorBoundary>
      </div>
    </div>
  );
};

export default MonitorView;
