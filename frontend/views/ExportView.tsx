import React, { useEffect, useState, useCallback } from 'react';
import { getArtifacts, getArtifactCode, downloadRunBundle } from '../services/api';

// ── Types ─────────────────────────────────────────────────────────────────────

interface ArtifactFile { name: string; type: string; size: string; size_bytes: number; }
interface ValidationSummary { passed: boolean | null; score: number | null; summary: { pass: number; warn: number; fail: number; total: number }; }
interface RunBundle {
  run_id: string;
  graph_name: string;
  completed_at?: string;
  elapsed?: string;
  has_code: boolean;
  files: ArtifactFile[];
  total_files: number;
  validation?: ValidationSummary | null;
}

// ── Syntax-highlighted code block ────────────────────────────────────────────

const CodeBlock: React.FC<{ code: string; lang?: string; maxHeight?: string }> = ({
  code, lang = 'python', maxHeight = '500px'
}) => {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="relative rounded-xl overflow-hidden border border-slate-700 bg-slate-950">
      <div className="flex items-center justify-between px-4 py-2 bg-slate-800 border-b border-slate-700">
        <span className="text-xs text-slate-400 font-mono">{lang}</span>
        <button onClick={copy}
          className="text-xs text-slate-400 hover:text-white flex items-center gap-1.5 transition-colors">
          <i className={`fas ${copied ? 'fa-check text-emerald-400' : 'fa-copy'}`}></i>
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <pre style={{ maxHeight, overflowY: 'auto' }}
        className="p-4 text-[11px] text-emerald-300 font-mono leading-relaxed whitespace-pre-wrap break-words">
        {code}
      </pre>
    </div>
  );
};

// ── File icon ─────────────────────────────────────────────────────────────────

const FileIcon: React.FC<{ name: string }> = ({ name }) => {
  const icons: Record<string, string> = {
    'agent.py': 'fa-robot text-indigo-400',
    'requirements.txt': 'fa-box-open text-amber-400',
    '.env.example': 'fa-key text-rose-400',
    'workflow_config.json': 'fa-brackets-curly text-teal-400',
    'run_result.json': 'fa-clipboard-check text-emerald-400',
    'README.md': 'fa-book text-blue-400',
    'validation_report.json': 'fa-shield-check text-violet-400',
  };
  const cls = icons[name] ?? 'fa-file text-slate-400';
  return <i className={`fas ${cls} text-base`}></i>;
};

// ── Validation badge ───────────────────────────────────────────────────────────

const ValidationBadge: React.FC<{ v: ValidationSummary | null | undefined }> = ({ v }) => {
  if (!v || v.score === null) return null;
  const passed = v.passed;
  const score = v.score ?? 0;
  const bg = passed
    ? score >= 90 ? 'bg-emerald-100 text-emerald-700 border-emerald-200'
                  : 'bg-amber-100 text-amber-700 border-amber-200'
    : 'bg-rose-100 text-rose-700 border-rose-200';
  const icon = passed ? (score >= 90 ? 'fa-shield-check' : 'fa-triangle-exclamation') : 'fa-shield-xmark';
  const label = passed ? `✓ ${score}%` : `✗ ${score}%`;
  return (
    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border flex items-center gap-1 ${bg}`}>
      <i className={`fas ${icon} text-[9px]`}></i>{label}
    </span>
  );
};

// ── Run card ──────────────────────────────────────────────────────────────────

const RunCard: React.FC<{ run: RunBundle; isSelected: boolean; onSelect: () => void; }> = ({
  run, isSelected, onSelect
}) => {
  const date = run.completed_at
    ? new Date(run.completed_at).toLocaleString()
    : 'Unknown';
  return (
    <div
      onClick={onSelect}
      className={`cursor-pointer rounded-2xl border-2 p-4 transition-all ${
        isSelected
          ? 'border-indigo-500 bg-indigo-50/60 shadow-md shadow-indigo-100'
          : 'border-slate-200 bg-white hover:border-indigo-300 hover:shadow-sm'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
            isSelected ? 'bg-indigo-600' : 'bg-slate-100'
          }`}>
            <i className={`fas fa-box text-sm ${isSelected ? 'text-white' : 'text-slate-500'}`}></i>
          </div>
          <div>
            <div className="font-bold text-slate-800 text-sm">{run.graph_name}</div>
            <div className="text-xs text-slate-400 mt-0.5 font-mono">{run.run_id.slice(0, 16)}…</div>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          {run.has_code && (
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 border border-emerald-200">
              ✓ CODE READY
            </span>
          )}
          <ValidationBadge v={run.validation} />
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {run.files.map(f => (
          <span key={f.name}
            className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-lg bg-slate-50 border border-slate-200 text-slate-600">
            <FileIcon name={f.name} />
            <span className="font-mono">{f.name}</span>
            <span className="text-slate-400">{f.size}</span>
          </span>
        ))}
      </div>
      <div className="mt-2 flex items-center gap-3 text-[10px] text-slate-400">
        <span><i className="fas fa-clock mr-1"></i>{run.elapsed ?? '—'}</span>
        <span><i className="fas fa-calendar-alt mr-1"></i>{date}</span>
        <span><i className="fas fa-files mr-1"></i>{run.total_files} files</span>
      </div>
    </div>
  );
};

// ── Tabs for the code preview panel ──────────────────────────────────────────

const PREVIEW_TABS = [
  { id: 'agent', label: 'agent.py', icon: 'fa-robot', key: 'agent_py', lang: 'python' },
  { id: 'req', label: 'requirements.txt', icon: 'fa-box-open', key: 'requirements_txt', lang: 'text' },
  { id: 'env', label: '.env.example', icon: 'fa-key', key: 'env_example', lang: 'bash' },
  { id: 'readme', label: 'README.md', icon: 'fa-book', key: 'readme', lang: 'markdown' },
  { id: 'validation', label: 'Validation', icon: 'fa-shield-halved', key: 'validation_report', lang: 'json' },
] as const;

type TabId = typeof PREVIEW_TABS[number]['id'];

// ── Validation Report Panel ────────────────────────────────────────────────────

const STATUS_STYLE: Record<string, { row: string; badge: string; icon: string }> = {
  pass:  { row: 'bg-emerald-50 border-emerald-100', badge: 'bg-emerald-100 text-emerald-700', icon: 'fa-circle-check text-emerald-500' },
  warn:  { row: 'bg-amber-50  border-amber-100',  badge: 'bg-amber-100  text-amber-700',  icon: 'fa-triangle-exclamation text-amber-500' },
  fail:  { row: 'bg-rose-50   border-rose-100',   badge: 'bg-rose-100   text-rose-700',   icon: 'fa-circle-xmark text-rose-500' },
};

const ValidationReportPanel: React.FC<{ report: any }> = ({ report }) => {
  if (!report) return (
    <div className="flex flex-col items-center justify-center h-64 text-slate-400">
      <i className="fas fa-shield-halved text-3xl mb-3"></i>
      <p className="text-sm">No validation report for this run.</p>
      <p className="text-xs mt-1 text-slate-300">Re-run the workflow to generate an up-to-date report.</p>
    </div>
  );
  const { passed, score, checks = [], summary = {} } = report;
  const scoreColor = passed
    ? score >= 90 ? 'text-emerald-600' : 'text-amber-600'
    : 'text-rose-600';
  const cats = [...new Set<string>(checks.map((c: any) => c.category))];
  return (
    <div className="space-y-4 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 420px)' }}>
      {/* Score header */}
      <div className="flex items-center gap-6 p-4 rounded-2xl bg-slate-50 border border-slate-100">
        <div className="text-center">
          <div className={`text-4xl font-black ${scoreColor}`}>{score ?? '—'}<span className="text-xl font-bold text-slate-400">%</span></div>
          <div className="text-[10px] text-slate-400 mt-0.5 font-semibold uppercase tracking-wide">Trust Score</div>
        </div>
        <div className="flex-1 grid grid-cols-3 gap-3">
          {[['pass', 'emerald', summary.pass ?? 0], ['warn', 'amber', summary.warn ?? 0], ['fail', 'rose', summary.fail ?? 0]].map(([s, c, n]) => (
            <div key={s as string} className={`rounded-xl p-3 text-center bg-${c}-50 border border-${c}-100`}>
              <div className={`text-2xl font-bold text-${c}-600`}>{n as number}</div>
              <div className={`text-[10px] font-semibold text-${c}-500 uppercase`}>{s as string}</div>
            </div>
          ))}
        </div>
        <div className={`flex items-center gap-2 px-4 py-2 rounded-xl font-bold text-sm ${passed ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
          <i className={`fas ${passed ? 'fa-shield-check' : 'fa-shield-xmark'}`}></i>
          {passed ? 'PASSED' : 'FAILED'}
        </div>
      </div>

      {/* Checks grouped by category */}
      {cats.map(cat => {
        const catChecks = checks.filter((c: any) => c.category === cat);
        return (
          <div key={cat} className="rounded-xl border border-slate-100 overflow-hidden">
            <div className="px-4 py-2 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
              <span className="text-xs font-bold text-slate-600 uppercase tracking-wide">{cat}</span>
              <div className="flex gap-1">
                {(['pass','warn','fail'] as const).map(s => {
                  const n = catChecks.filter((c: any) => c.status === s).length;
                  if (!n) return null;
                  return <span key={s} className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${STATUS_STYLE[s].badge}`}>{n} {s}</span>;
                })}
              </div>
            </div>
            <div className="divide-y divide-slate-50">
              {catChecks.map((c: any) => {
                const st = STATUS_STYLE[c.status] || STATUS_STYLE.pass;
                return (
                  <div key={c.id} className={`px-4 py-2.5 flex items-start gap-3 border-l-2 ${st.row}`}>
                    <i className={`fas ${st.icon} text-sm mt-0.5 flex-shrink-0`}></i>
                    <div className="min-w-0">
                      <div className="text-xs font-medium text-slate-700">{c.description}</div>
                      {c.detail && (
                        <pre className="mt-1 text-[10px] text-slate-500 whitespace-pre-wrap break-words font-mono bg-white/60 rounded px-2 py-1 border border-slate-100">
                          {c.detail}
                        </pre>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
};



const ExportView: React.FC = () => {
  const [runs, setRuns] = useState<RunBundle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [codeData, setCodeData] = useState<any>(null);
  const [codeLoading, setCodeLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<TabId>('agent');
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const data = await getArtifacts();
      setRuns(data);
      if (data.length > 0 && !selectedRunId) {
        setSelectedRunId(data[0].run_id);
      }
    } catch (e: any) {
      setError(e?.message || 'Failed to load artifacts');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!selectedRunId) { setCodeData(null); return; }
    setCodeLoading(true); setCodeData(null);
    getArtifactCode(selectedRunId)
      .then(d => { setCodeData(d); setActiveTab('agent'); })
      .catch(() => setCodeData(null))
      .finally(() => setCodeLoading(false));
  }, [selectedRunId]);

  const handleDownload = async () => {
    if (!selectedRunId) return;
    setDownloading(true);
    try {
      const blob = await downloadRunBundle(selectedRunId);
      const run = runs.find(r => r.run_id === selectedRunId);
      const name = (run?.graph_name ?? 'workflow').replace(/[^\w\-]/g, '_');
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `${name}_${selectedRunId.slice(0, 8)}.zip`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e?.message || 'Download failed');
    } finally {
      setDownloading(false);
    }
  };

  const selectedRun = runs.find(r => r.run_id === selectedRunId);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-indigo-50/30 p-6">
      {/* ── Header ── */}
      <div className="max-w-7xl mx-auto mb-8">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <div className="w-10 h-10 rounded-2xl bg-indigo-600 flex items-center justify-center">
                <i className="fas fa-apple-whole text-white text-lg"></i>
              </div>
              <div>
                <h1 className="text-2xl font-bold text-slate-800">Artifact Workbench</h1>
                <p className="text-sm text-slate-500">
                  Your workflow runs produce <strong className="text-indigo-600">deployable agentic code</strong> — take it anywhere.
                </p>
              </div>
            </div>
          </div>
          <button onClick={load}
            className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 text-sm font-medium transition-colors shadow-sm">
            <i className="fas fa-arrows-rotate"></i> Refresh
          </button>
        </div>

        {/* Value statement */}
        <div className="mt-4 grid grid-cols-3 gap-4">
          {[
            { icon: 'fa-seedling', color: 'text-emerald-600 bg-emerald-50', title: 'You build the template', body: 'Define nodes, edges, LLM settings, guardrails, tools in the Builder.' },
            { icon: 'fa-play-circle', color: 'text-indigo-600 bg-indigo-50', title: 'You run to validate', body: 'The workbench runs the workflow against LM Studio to prove it works.' },
            { icon: 'fa-box-archive', color: 'text-amber-600 bg-amber-50', title: 'You ship the apple 🍎', body: 'Download the generated Python code — fully standalone, deploy anywhere.' },
          ].map(s => (
            <div key={s.title} className={`rounded-2xl p-4 border border-slate-100 bg-white`}>
              <div className={`w-8 h-8 rounded-xl flex items-center justify-center ${s.color} mb-2`}>
                <i className={`fas ${s.icon} text-sm`}></i>
              </div>
              <div className="font-semibold text-slate-800 text-sm">{s.title}</div>
              <div className="text-xs text-slate-500 mt-0.5">{s.body}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Main layout: run list + code preview ── */}
      <div className="max-w-7xl mx-auto flex gap-6">

        {/* Left: run list */}
        <div className="w-80 flex-shrink-0 flex flex-col gap-3">
          <div className="flex items-center justify-between mb-1">
            <h2 className="font-bold text-slate-700 text-sm">
              <i className="fas fa-history mr-2 text-indigo-400"></i>
              Completed Runs ({runs.length})
            </h2>
          </div>

          {loading ? (
            <div className="text-center py-12 text-slate-400">
              <i className="fas fa-spinner fa-spin text-2xl mb-3 block"></i>
              <p className="text-sm">Loading artifact bundles…</p>
            </div>
          ) : error ? (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-rose-600 text-sm">
              <i className="fas fa-triangle-exclamation mr-2"></i>{error}
            </div>
          ) : runs.length === 0 ? (
            <div className="rounded-2xl border-2 border-dashed border-slate-200 p-8 text-center">
              <i className="fas fa-box-open text-3xl text-slate-200 mb-3 block"></i>
              <p className="text-slate-500 font-medium text-sm">No artifacts yet</p>
              <p className="text-slate-400 text-xs mt-1">
                Run a workflow in <strong>Builder → Run</strong> to generate your first deployable bundle.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-3 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 340px)' }}>
              {runs.map(run => (
                <RunCard
                  key={run.run_id}
                  run={run}
                  isSelected={selectedRunId === run.run_id}
                  onSelect={() => setSelectedRunId(run.run_id)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Right: code preview panel */}
        <div className="flex-1 min-w-0">
          {!selectedRun ? (
            <div className="flex flex-col items-center justify-center h-96 rounded-2xl border-2 border-dashed border-slate-200 bg-white text-center">
              <i className="fas fa-arrow-left text-2xl text-slate-200 mb-3"></i>
              <p className="text-slate-400 text-sm">Select a run to preview its generated code</p>
            </div>
          ) : (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
              {/* Panel header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
                <div>
                  <div className="font-bold text-slate-800">{selectedRun.graph_name}</div>
                  <div className="text-xs text-slate-400 font-mono mt-0.5">{selectedRun.run_id}</div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleDownload}
                    disabled={downloading}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold transition-colors disabled:opacity-60 shadow-sm"
                  >
                    {downloading
                      ? <><i className="fas fa-spinner fa-spin"></i> Downloading…</>
                      : <><i className="fas fa-file-zipper"></i> Download Bundle (.zip)</>
                    }
                  </button>
                </div>
              </div>

              {/* File tabs */}
              <div className="flex border-b border-slate-100 px-6 gap-1 bg-slate-50/60 overflow-x-auto">
                {PREVIEW_TABS.map(tab => {
                  const isVal = tab.id === 'validation';
                  const vr = codeData?.validation_report;
                  const valPassed = vr?.passed;
                  const valScore = vr?.score;
                  return (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={`flex items-center gap-1.5 px-3 py-2.5 text-xs font-semibold border-b-2 transition-colors whitespace-nowrap ${
                        activeTab === tab.id
                          ? 'border-indigo-500 text-indigo-700 bg-white'
                          : 'border-transparent text-slate-500 hover:text-slate-700'
                      }`}
                    >
                      <i className={`fas ${tab.icon} text-[10px] ${isVal && vr ? (valPassed ? 'text-emerald-500' : 'text-rose-500') : ''}`}></i>
                      {tab.label}
                      {isVal && vr && (
                        <span className={`ml-1 text-[9px] font-bold px-1.5 py-0.5 rounded-full ${valPassed ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
                          {valScore}%
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Code content */}
              <div className="p-4">
                {codeLoading ? (
                  <div className="flex items-center justify-center h-64 text-slate-400">
                    <i className="fas fa-spinner fa-spin mr-2"></i> Loading code…
                  </div>
                ) : !codeData ? (
                  <div className="flex flex-col items-center justify-center h-64 text-slate-400">
                    <i className="fas fa-code-slash text-2xl mb-2"></i>
                    <p className="text-sm">agent.py not generated yet for this run</p>
                    <p className="text-xs text-slate-300 mt-1">Only completed runs produce artifact code</p>
                  </div>
                ) : activeTab === 'validation' ? (
                  <ValidationReportPanel report={codeData?.validation_report} />
                ) : (
                  <>
                    {/* Deployment instructions callout */}
                    {activeTab === 'agent' && (
                      <div className="mb-3 rounded-xl bg-indigo-50 border border-indigo-100 px-4 py-3 flex items-start gap-3">
                        <i className="fas fa-rocket text-indigo-500 mt-0.5"></i>
                        <div className="text-xs text-indigo-800">
                          <strong>This is your deployable agent.</strong> Copy <code className="bg-indigo-100 px-1 rounded">agent.py</code>,{' '}
                          <code className="bg-indigo-100 px-1 rounded">requirements.txt</code> and{' '}
                          <code className="bg-indigo-100 px-1 rounded">.env</code> to any server, Docker container, or cloud function.{' '}
                          No workbench dependency — fully standalone Python.
                        </div>
                      </div>
                    )}
                    <CodeBlock
                      code={codeData[PREVIEW_TABS.find(t => t.id === activeTab)!.key] || '# (empty)'}
                      lang={PREVIEW_TABS.find(t => t.id === activeTab)!.lang}
                      maxHeight="calc(100vh - 420px)"
                    />
                  </>
                )}
              </div>
            </div>
          )}
        </div>

      </div>
    </div>
  );
};

export default ExportView;
