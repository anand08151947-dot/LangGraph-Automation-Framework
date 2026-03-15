/**
 * ToolsView.tsx — MCP-7: Tool Management UI
 * Lists registered tools with health status, allows registration and unregistration.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { listTools, registerTool, unregisterTool, checkToolHealth } from '../services/api';

interface Tool {
  name: string;
  description?: string;
  version?: string;
  status?: string;
  health_url?: string;
  schema?: any;
}

const StatusBadge: React.FC<{ status?: string }> = ({ status }) => {
  const s = (status || 'unknown').toLowerCase();
  const cls =
    s === 'healthy' ? 'bg-emerald-100 text-emerald-700' :
    s === 'unhealthy' ? 'bg-rose-100 text-rose-700' :
    'bg-slate-100 text-slate-500';
  const icon = s === 'healthy' ? 'fa-check-circle' : s === 'unhealthy' ? 'fa-times-circle' : 'fa-question-circle';
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
      <i className={`fas ${icon} text-[10px]`}></i>{status || 'unknown'}
    </span>
  );
};

const ToolsView: React.FC = () => {
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const [healthLoading, setHealthLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  // Register form
  const [showRegister, setShowRegister] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', version: '1.0', health_url: '' });
  const [regLoading, setRegLoading] = useState(false);

  const notify = (type: 'success' | 'error', msg: string) => {
    setNotification({ type, msg });
    setTimeout(() => setNotification(null), 4000);
  };

  const fetchTools = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const data = await listTools();
      setTools(Array.isArray(data) ? data : data?.tools ?? []);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to load tools');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchTools(); }, [fetchTools]);

  const handleHealthCheck = async () => {
    setHealthLoading(true);
    try {
      const results = await checkToolHealth();
      const updated: Tool[] = Array.isArray(results) ? results : results?.health ?? [];
      setTools(prev => prev.map(t => {
        const fresh = updated.find((u: any) => u.name === t.name);
        return fresh ? { ...t, status: fresh.status } : t;
      }));
      notify('success', 'Health check complete');
    } catch {
      notify('error', 'Health check failed');
    } finally {
      setHealthLoading(false);
    }
  };

  const handleUnregister = async (name: string) => {
    if (!confirm(`Unregister tool "${name}"?`)) return;
    try {
      await unregisterTool(name);
      setTools(prev => prev.filter(t => t.name !== name));
      notify('success', `Tool "${name}" unregistered`);
    } catch (e: any) {
      notify('error', e?.response?.data?.detail || 'Unregister failed');
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    setRegLoading(true);
    try {
      const payload: any = { name: form.name.trim(), description: form.description, version: form.version };
      if (form.health_url.trim()) payload.health_url = form.health_url.trim();
      await registerTool(payload);
      notify('success', `Tool "${form.name}" registered`);
      setForm({ name: '', description: '', version: '1.0', health_url: '' });
      setShowRegister(false);
      fetchTools();
    } catch (e: any) {
      notify('error', e?.response?.data?.detail || 'Registration failed');
    } finally {
      setRegLoading(false);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Notification */}
      {notification && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-xl shadow-lg text-sm font-medium flex items-center gap-2 ${
          notification.type === 'success' ? 'bg-emerald-600 text-white' : 'bg-rose-600 text-white'}`}>
          <i className={`fas ${notification.type === 'success' ? 'fa-check-circle' : 'fa-times-circle'}`}></i>
          {notification.msg}
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Tool Registry</h1>
          <p className="text-sm text-slate-500 mt-0.5">Manage MCP tools — register, unregister, and check health</p>
        </div>
        <div className="flex gap-3">
          <button onClick={handleHealthCheck} disabled={healthLoading}
            className="px-4 py-2 border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-sm font-medium rounded-xl flex items-center gap-2 transition-all disabled:opacity-50">
            <i className={`fas fa-heartbeat ${healthLoading ? 'fa-spin' : ''}`}></i>
            {healthLoading ? 'Checking…' : 'Health Check'}
          </button>
          <button onClick={() => setShowRegister(v => !v)}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl flex items-center gap-2 transition-colors">
            <i className="fas fa-plus"></i> Register Tool
          </button>
        </div>
      </div>

      {/* Register panel */}
      {showRegister && (
        <form onSubmit={handleRegister} className="p-5 bg-indigo-50 border border-indigo-200 rounded-2xl space-y-4">
          <h3 className="text-sm font-bold text-indigo-800 flex items-center gap-2">
            <i className="fas fa-plug"></i> Register New Tool
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Name *</label>
              <input required value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                placeholder="my_tool" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Version</label>
              <input value={form.version} onChange={e => setForm(f => ({ ...f, version: e.target.value }))}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                placeholder="1.0" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Description</label>
              <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                placeholder="What this tool does" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Health URL (optional)</label>
              <input value={form.health_url} onChange={e => setForm(f => ({ ...f, health_url: e.target.value }))}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                placeholder="http://localhost:8001/health" />
            </div>
          </div>
          <div className="flex gap-3">
            <button type="submit" disabled={regLoading}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg flex items-center gap-2 disabled:opacity-50">
              <i className={`fas ${regLoading ? 'fa-spinner fa-spin' : 'fa-save'}`}></i>
              {regLoading ? 'Registering…' : 'Register'}
            </button>
            <button type="button" onClick={() => setShowRegister(false)}
              className="px-4 py-2 border border-slate-200 bg-white text-slate-700 text-sm font-medium rounded-lg hover:bg-slate-50">
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Error */}
      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-sm">
          <i className="fas fa-exclamation-triangle mr-2"></i>{error}
          <button onClick={fetchTools} className="ml-3 underline font-medium">Retry</button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-20 bg-slate-100 rounded-2xl animate-pulse" />
          ))}
        </div>
      )}

      {/* Empty */}
      {!loading && !error && tools.length === 0 && (
        <div className="flex flex-col items-center py-20 text-center">
          <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mb-4">
            <i className="fas fa-plug text-slate-400 text-2xl"></i>
          </div>
          <h3 className="text-lg font-semibold text-slate-800 mb-1">No tools registered</h3>
          <p className="text-sm text-slate-500 mb-4">Register a tool to see it here.</p>
          <button onClick={() => setShowRegister(true)}
            className="px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-xl">
            <i className="fas fa-plus mr-2"></i>Register First Tool
          </button>
        </div>
      )}

      {/* Tools table */}
      {!loading && !error && tools.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-500 uppercase tracking-wider">
                <th className="px-5 py-3 text-left">Tool Name</th>
                <th className="px-5 py-3 text-left">Description</th>
                <th className="px-5 py-3 text-left">Version</th>
                <th className="px-5 py-3 text-left">Status</th>
                <th className="px-5 py-3 text-left">Health URL</th>
                <th className="px-5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {tools.map((tool) => (
                <tr key={tool.name} className="hover:bg-slate-50 transition-colors">
                  <td className="px-5 py-4 font-mono font-bold text-slate-800">{tool.name}</td>
                  <td className="px-5 py-4 text-slate-500 max-w-xs truncate">{tool.description || <span className="text-slate-300 italic">—</span>}</td>
                  <td className="px-5 py-4 text-slate-600">{tool.version || '1.0'}</td>
                  <td className="px-5 py-4"><StatusBadge status={tool.status} /></td>
                  <td className="px-5 py-4 font-mono text-xs text-slate-400 truncate max-w-[180px]">
                    {tool.health_url || <span className="text-slate-300 italic">—</span>}
                  </td>
                  <td className="px-5 py-4 text-right">
                    <button onClick={() => handleUnregister(tool.name)}
                      className="px-3 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-50 border border-rose-200 rounded-lg transition-colors">
                      <i className="fas fa-trash-alt mr-1"></i>Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-slate-400 text-center">
        {tools.length} tool{tools.length !== 1 ? 's' : ''} registered · Click "Health Check" to probe live status
      </p>
    </div>
  );
};

export default ToolsView;
