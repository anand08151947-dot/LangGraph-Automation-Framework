/**
 * AuditLogView.tsx — FE-UX-8: Audit Log Viewer
 *
 * Shows guardrail violations and observability events for compliance and debugging.
 * Backend endpoints:
 *   GET /guardrail-violations[?session_id=…]  — violation audit trail
 *   GET /events/{session_id}                   — structured observability events
 */

import React, { useState, useCallback } from 'react';
import { getGuardrailViolations, getEvents } from '../services/api';

interface Violation {
  id: number;
  ts: number;
  session_id: string;
  run_id: string;
  check_name: string;
  action: string;
  content_hash: string;
}

interface ObsEvent {
  ts?: number;
  event_type?: string;
  session_id?: string;
  node_id?: string;
  [key: string]: any;
}

type TabId = 'violations' | 'events';

const ROWS_PER_PAGE = 20;

function formatTs(ts: number): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString();
}

function ActionBadge({ action }: { action: string }) {
  const colors: Record<string, string> = {
    block: 'bg-red-100 text-red-700',
    redact: 'bg-amber-100 text-amber-700',
    approve: 'bg-green-100 text-green-700',
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${colors[action] ?? 'bg-slate-100 text-slate-600'}`}>
      {action}
    </span>
  );
}

const AuditLogView: React.FC = () => {
  const [tab, setTab] = useState<TabId>('violations');

  // Violations state
  const [filterSession, setFilterSession] = useState('');
  const [violations, setViolations] = useState<Violation[] | null>(null);
  const [vLoading, setVLoading] = useState(false);
  const [vError, setVError] = useState('');
  const [vPage, setVPage] = useState(1);

  // Events state
  const [eventsSession, setEventsSession] = useState('');
  const [events, setEvents] = useState<ObsEvent[] | null>(null);
  const [eLoading, setELoading] = useState(false);
  const [eError, setEError] = useState('');
  const [ePage, setEPage] = useState(1);

  const loadViolations = useCallback(async () => {
    setVLoading(true);
    setVError('');
    try {
      const data = await getGuardrailViolations(filterSession || undefined);
      setViolations(Array.isArray(data) ? data : (data as any).violations ?? []);
      setVPage(1);
    } catch (e: any) {
      setVError(e?.message ?? 'Failed to load violations');
    } finally {
      setVLoading(false);
    }
  }, [filterSession]);

  const loadEvents = useCallback(async () => {
    if (!eventsSession.trim()) {
      setEError('Enter a session ID to load events');
      return;
    }
    setELoading(true);
    setEError('');
    try {
      const data = await getEvents(eventsSession.trim());
      setEvents(Array.isArray(data) ? data : (data as any).events ?? []);
      setEPage(1);
    } catch (e: any) {
      setEError(e?.message ?? 'Failed to load events');
    } finally {
      setELoading(false);
    }
  }, [eventsSession]);

  // Pagination helpers
  const paginate = <T,>(arr: T[], page: number) =>
    arr.slice((page - 1) * ROWS_PER_PAGE, page * ROWS_PER_PAGE);

  const PageControls = ({
    page, total, onPage,
  }: { page: number; total: number; onPage: (p: number) => void }) => {
    const pages = Math.max(1, Math.ceil(total / ROWS_PER_PAGE));
    if (pages <= 1) return null;
    return (
      <div className="flex items-center gap-1 justify-end pt-2">
        <button onClick={() => onPage(Math.max(1, page - 1))} disabled={page === 1}
          className="px-2 py-1 text-xs rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-100">
          <i className="fas fa-chevron-left" />
        </button>
        <span className="text-xs text-slate-500 px-2">Page {page} / {pages}</span>
        <button onClick={() => onPage(Math.min(pages, page + 1))} disabled={page === pages}
          className="px-2 py-1 text-xs rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-100">
          <i className="fas fa-chevron-right" />
        </button>
      </div>
    );
  };

  const tabs: { id: TabId; label: string; icon: string }[] = [
    { id: 'violations', label: 'Guardrail Violations', icon: 'fa-shield-alt' },
    { id: 'events', label: 'Observability Events', icon: 'fa-stream' },
  ];

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
          <i className="fas fa-clipboard-list text-indigo-500"></i> Audit Log
        </h1>
        <p className="text-slate-500 mt-1 text-sm">Guardrail violation history and observability events for compliance and debugging.</p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-slate-200 mb-6">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors flex items-center gap-2
              ${tab === t.id ? 'bg-white border border-b-white border-slate-200 text-indigo-600' : 'text-slate-500 hover:text-slate-700'}`}
          >
            <i className={`fas ${t.icon}`}></i> {t.label}
          </button>
        ))}
      </div>

      {/* ── Violations Tab ─────────────────────────────────────── */}
      {tab === 'violations' && (
        <div>
          {/* Filter bar */}
          <div className="flex gap-3 mb-5">
            <input
              type="text"
              value={filterSession}
              onChange={e => setFilterSession(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && loadViolations()}
              placeholder="Filter by session ID (optional)"
              className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
            <button
              onClick={loadViolations}
              disabled={vLoading}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg disabled:opacity-50 transition-colors flex items-center gap-2"
            >
              <i className={`fas ${vLoading ? 'fa-spinner fa-spin' : 'fa-search'}`}></i>
              {violations === null ? 'Load Violations' : 'Refresh'}
            </button>
          </div>

          {vError && (
            <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
              <i className="fas fa-exclamation-triangle mr-2"></i>{vError}
            </div>
          )}

          {violations !== null && (
            <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
                <span className="text-sm font-semibold text-slate-600">
                  {violations.length} violation{violations.length !== 1 ? 's' : ''}
                  {filterSession && ` · session: ${filterSession}`}
                </span>
                {violations.length > 0 && (
                  <button
                    onClick={() => {
                      const csv = [
                        'id,timestamp,session_id,run_id,check,action,content_hash',
                        ...violations.map(v =>
                          `${v.id},"${formatTs(v.ts)}","${v.session_id}","${v.run_id}","${v.check_name}","${v.action}","${v.content_hash}"`
                        ),
                      ].join('\n');
                      const blob = new Blob([csv], { type: 'text/csv' });
                      const a = document.createElement('a');
                      a.href = URL.createObjectURL(blob);
                      a.download = 'guardrail_violations.csv';
                      a.click();
                    }}
                    className="text-xs text-indigo-600 hover:underline font-medium flex items-center gap-1"
                  >
                    <i className="fas fa-download"></i> Export CSV
                  </button>
                )}
              </div>

              {violations.length === 0 ? (
                <div className="p-8 text-center text-slate-400 text-sm">
                  <i className="fas fa-check-circle text-2xl text-green-400 mb-2 block"></i>
                  No violations found
                </div>
              ) : (
                <>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="bg-slate-50 border-b border-slate-100">
                        <tr>
                          {['ID', 'Timestamp', 'Session', 'Run ID', 'Check', 'Action', 'Content Hash'].map(h => (
                            <th key={h} className="px-3 py-2.5 text-left font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-50">
                        {paginate(violations, vPage).map(v => (
                          <tr key={v.id} className="hover:bg-slate-50 transition-colors">
                            <td className="px-3 py-2 font-mono text-slate-400">{v.id}</td>
                            <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{formatTs(v.ts)}</td>
                            <td className="px-3 py-2 font-mono text-slate-600 max-w-[120px] truncate" title={v.session_id}>{v.session_id || '—'}</td>
                            <td className="px-3 py-2 font-mono text-slate-600 max-w-[120px] truncate" title={v.run_id}>{v.run_id || '—'}</td>
                            <td className="px-3 py-2">
                              <span className="inline-block px-2 py-0.5 bg-indigo-50 text-indigo-700 rounded text-xs font-semibold">{v.check_name}</span>
                            </td>
                            <td className="px-3 py-2"><ActionBadge action={v.action} /></td>
                            <td className="px-3 py-2 font-mono text-slate-400 max-w-[100px] truncate" title={v.content_hash}>{v.content_hash}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="px-4 py-2 border-t border-slate-100">
                    <PageControls page={vPage} total={violations.length} onPage={setVPage} />
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Events Tab ─────────────────────────────────────────── */}
      {tab === 'events' && (
        <div>
          <div className="flex gap-3 mb-5">
            <input
              type="text"
              value={eventsSession}
              onChange={e => setEventsSession(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && loadEvents()}
              placeholder="Enter session ID to load events"
              className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
            <button
              onClick={loadEvents}
              disabled={eLoading}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg disabled:opacity-50 transition-colors flex items-center gap-2"
            >
              <i className={`fas ${eLoading ? 'fa-spinner fa-spin' : 'fa-search'}`}></i>
              Load Events
            </button>
          </div>

          {eError && (
            <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
              <i className="fas fa-exclamation-triangle mr-2"></i>{eError}
            </div>
          )}

          {events !== null && (
            <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-100">
                <span className="text-sm font-semibold text-slate-600">
                  {events.length} event{events.length !== 1 ? 's' : ''} · session: {eventsSession}
                </span>
              </div>
              {events.length === 0 ? (
                <div className="p-8 text-center text-slate-400 text-sm">
                  <i className="fas fa-inbox text-2xl mb-2 block"></i>
                  No events found for this session
                </div>
              ) : (
                <>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="bg-slate-50 border-b border-slate-100">
                        <tr>
                          {['Timestamp', 'Event Type', 'Node ID', 'Details'].map(h => (
                            <th key={h} className="px-3 py-2.5 text-left font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-50">
                        {paginate(events, ePage).map((ev, i) => {
                          const { ts, event_type, session_id: _s, node_id, ...rest } = ev;
                          return (
                            <tr key={i} className="hover:bg-slate-50 transition-colors align-top">
                              <td className="px-3 py-2 whitespace-nowrap text-slate-500">{ts ? formatTs(ts) : '—'}</td>
                              <td className="px-3 py-2">
                                <span className="inline-block px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs font-semibold whitespace-nowrap">
                                  {event_type ?? '—'}
                                </span>
                              </td>
                              <td className="px-3 py-2 font-mono text-slate-500">{node_id ?? '—'}</td>
                              <td className="px-3 py-2 text-slate-500 max-w-xs">
                                {Object.keys(rest).length > 0 ? (
                                  <pre className="text-[10px] bg-slate-50 rounded p-1 overflow-x-auto max-h-16">
                                    {JSON.stringify(rest, null, 2)}
                                  </pre>
                                ) : '—'}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  <div className="px-4 py-2 border-t border-slate-100">
                    <PageControls page={ePage} total={events.length} onPage={setEPage} />
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default AuditLogView;
