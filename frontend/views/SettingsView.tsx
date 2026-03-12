
import React, { useState, useEffect } from 'react';
import { Card, Button } from '../components/Shared';
import { getConfig, updateLmStudioConfig, testLlmConnection, updateLlmConfig } from '../services/api';

// ── Connection test badge ────────────────────────────────────────────────────
type TestState = 'idle' | 'testing' | 'ok' | 'error';
interface TestResult { state: TestState; latency_ms?: number; error?: string }

const ConnectionBadge: React.FC<{ result: TestResult }> = ({ result }) => {
  if (result.state === 'idle') return null;
  if (result.state === 'testing') return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-100 text-amber-700 text-xs font-semibold">
      <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
      </svg>
      Testing…
    </span>
  );
  if (result.state === 'ok') return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100 text-emerald-700 text-xs font-semibold">
      ✅ Connected · {result.latency_ms}ms
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-rose-100 text-rose-700 text-xs font-semibold">
      ❌ Failed: {result.error}
    </span>
  );
};

// ── Reusable field components ────────────────────────────────────────────────
const Field: React.FC<{ label: string; hint?: string; children: React.ReactNode }> = ({ label, hint, children }) => (
  <div className="space-y-1.5">
    <label className="text-sm font-bold text-slate-700">{label}</label>
    {children}
    {hint && <p className="text-xs text-slate-400">{hint}</p>}
  </div>
);

const TextInput: React.FC<React.InputHTMLAttributes<HTMLInputElement>> = (props) => (
  <input {...props} className="w-full pl-4 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-lg font-mono text-sm focus:ring-2 focus:ring-indigo-500/20 outline-none" />
);

const Select: React.FC<React.SelectHTMLAttributes<HTMLSelectElement>> = ({ children, ...props }) => (
  <select {...props} className="w-full pl-4 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 outline-none">
    {children}
  </select>
);

// ── Provider tab types ───────────────────────────────────────────────────────
type Provider = 'lm_studio' | 'openai' | 'gemini' | 'anthropic' | 'ollama';
const TABS: { id: Provider; label: string }[] = [
  { id: 'lm_studio', label: 'LM Studio' },
  { id: 'openai', label: 'OpenAI' },
  { id: 'gemini', label: 'Gemini' },
  { id: 'anthropic', label: 'Anthropic' },
  { id: 'ollama', label: 'Ollama' },
];

// ── LM Studio panel ──────────────────────────────────────────────────────────
const LmStudioPanel: React.FC<{ initialCfg: any }> = ({ initialCfg }) => {
  const [baseUrl, setBaseUrl] = useState('http://localhost:1234');
  const [model, setModel] = useState('local-model');
  const [fetchedModels, setFetchedModels] = useState<string[]>([]);
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<TestResult>({ state: 'idle' });
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    if (initialCfg?.lm_studio?.base_url) setBaseUrl(initialCfg.lm_studio.base_url);
    else if (initialCfg?.lm_studio?.url) setBaseUrl(initialCfg.lm_studio.url.replace('/v1/completions', ''));
    if (initialCfg?.lm_studio?.model) setModel(initialCfg.lm_studio.model);
  }, [initialCfg]);

  const fetchModels = async () => {
    setFetching(true); setFetchError(null); setFetchedModels([]);
    try {
      const res = await fetch(`${baseUrl.replace(/\/$/, '')}/v1/models`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const ids: string[] = (data.data || []).map((m: any) => m.id || m.name || String(m));
      setFetchedModels(ids);
      if (ids.length) setModel(ids[0]);
    } catch (e: any) {
      setFetchError(e?.message || 'Failed to fetch models');
    } finally {
      setFetching(false);
    }
  };

  const runTest = async () => {
    setTestResult({ state: 'testing' });
    try {
      const r = await testLlmConnection({ provider: 'lm_studio', base_url: baseUrl, model });
      setTestResult(r.ok ? { state: 'ok', latency_ms: r.latency_ms } : { state: 'error', error: r.error });
    } catch (e: any) {
      setTestResult({ state: 'error', error: e?.message || 'Request failed' });
    }
  };

  const save = async () => {
    setSaving(true); setSaveMsg(null);
    try {
      await updateLmStudioConfig(`${baseUrl.replace(/\/$/, '')}/v1/completions`, model);
      await updateLlmConfig({ provider: 'lm_studio', base_url: baseUrl, model });
      setSaveMsg({ type: 'success', text: 'LM Studio config saved.' });
    } catch (e: any) {
      setSaveMsg({ type: 'error', text: e?.message || 'Save failed.' });
    } finally { setSaving(false); }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3 p-3 border border-indigo-100 bg-indigo-50 rounded-xl">
        <div className="w-10 h-10 rounded-lg bg-indigo-600 flex items-center justify-center text-white flex-shrink-0">
          <i className="fas fa-robot"></i>
        </div>
        <div>
          <p className="font-bold text-slate-800 text-sm">LM Studio</p>
          <p className="text-xs text-indigo-600">Local LLM — runs on your machine</p>
        </div>
      </div>
      <Field label="Server Base URL" hint="Default port 1234.">
        <TextInput value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="http://localhost:1234" />
      </Field>
      <Field label="Model Name" hint="Manually enter or fetch from server below.">
        <TextInput value={model} onChange={e => setModel(e.target.value)} placeholder="local-model" />
      </Field>
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" onClick={fetchModels} isLoading={fetching}>
          <i className="fas fa-download mr-2"></i>Fetch Available Models
        </Button>
        {fetchError && <span className="text-xs text-rose-500">{fetchError}</span>}
      </div>
      {fetchedModels.length > 0 && (
        <Field label="Available Models">
          <Select value={model} onChange={e => setModel(e.target.value)}>
            {fetchedModels.map(m => <option key={m} value={m}>{m}</option>)}
          </Select>
        </Field>
      )}
      <div className="flex flex-wrap items-center gap-3 pt-1">
        <Button variant="secondary" onClick={runTest} disabled={testResult.state === 'testing'}>
          <i className="fas fa-plug mr-2"></i>Test Connection
        </Button>
        <ConnectionBadge result={testResult} />
      </div>
      {saveMsg && <p className={`text-sm font-medium ${saveMsg.type === 'success' ? 'text-emerald-600' : 'text-rose-500'}`}>{saveMsg.text}</p>}
      <Button onClick={save} isLoading={saving} className="w-fit">
        <i className="fas fa-save mr-2"></i>Save LM Studio Config
      </Button>
    </div>
  );
};

// ── Generic API-key provider panel ──────────────────────────────────────────
interface ApiKeyPanelProps {
  provider: 'openai' | 'gemini' | 'anthropic';
  label: string;
  models: string[];
  initialKey?: string;
  initialModel?: string;
}

const ApiKeyPanel: React.FC<ApiKeyPanelProps> = ({ provider, label, models, initialKey = '', initialModel }) => {
  const [apiKey, setApiKey] = useState(initialKey);
  const [model, setModel] = useState(initialModel || models[0]);
  const [testResult, setTestResult] = useState<TestResult>({ state: 'idle' });
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => { if (initialKey) setApiKey(initialKey); }, [initialKey]);
  useEffect(() => { if (initialModel) setModel(initialModel); }, [initialModel]);

  const runTest = async () => {
    setTestResult({ state: 'testing' });
    try {
      const r = await testLlmConnection({ provider, api_key: apiKey, model });
      setTestResult(r.ok ? { state: 'ok', latency_ms: r.latency_ms } : { state: 'error', error: r.error });
    } catch (e: any) {
      setTestResult({ state: 'error', error: e?.message || 'Request failed' });
    }
  };

  const save = async () => {
    setSaving(true); setSaveMsg(null);
    try {
      await updateLlmConfig({ provider, api_key: apiKey, model });
      setSaveMsg({ type: 'success', text: `${label} config saved.` });
    } catch (e: any) {
      setSaveMsg({ type: 'error', text: e?.message || 'Save failed.' });
    } finally { setSaving(false); }
  };

  return (
    <div className="space-y-5">
      <Field label="API Key">
        <TextInput type="password" value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder={provider === 'openai' ? 'sk-...' : 'Enter API key'} />
      </Field>
      <Field label="Model">
        <Select value={model} onChange={e => setModel(e.target.value)}>
          {models.map(m => <option key={m} value={m}>{m}</option>)}
        </Select>
      </Field>
      <div className="flex flex-wrap items-center gap-3 pt-1">
        <Button variant="secondary" onClick={runTest} disabled={testResult.state === 'testing'}>
          <i className="fas fa-plug mr-2"></i>Test Connection
        </Button>
        <ConnectionBadge result={testResult} />
      </div>
      {saveMsg && <p className={`text-sm font-medium ${saveMsg.type === 'success' ? 'text-emerald-600' : 'text-rose-500'}`}>{saveMsg.text}</p>}
      <Button onClick={save} isLoading={saving} className="w-fit">
        <i className="fas fa-save mr-2"></i>Save {label} Config
      </Button>
    </div>
  );
};

// ── Ollama panel ─────────────────────────────────────────────────────────────
const OllamaPanel: React.FC<{ initialCfg: any }> = ({ initialCfg }) => {
  const [url, setUrl] = useState('http://localhost:11434');
  const [model, setModel] = useState('llama3');
  const [fetchedModels, setFetchedModels] = useState<string[]>([]);
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<TestResult>({ state: 'idle' });
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    if (initialCfg?.ollama?.url) setUrl(initialCfg.ollama.url);
    if (initialCfg?.ollama?.model) setModel(initialCfg.ollama.model);
  }, [initialCfg]);

  const fetchModels = async () => {
    setFetching(true); setFetchError(null); setFetchedModels([]);
    try {
      const res = await fetch(`${url.replace(/\/$/, '')}/api/tags`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const names: string[] = (data.models || []).map((m: any) => m.name || String(m));
      setFetchedModels(names);
      if (names.length) setModel(names[0]);
    } catch (e: any) {
      setFetchError(e?.message || 'Failed to fetch models');
    } finally { setFetching(false); }
  };

  const runTest = async () => {
    setTestResult({ state: 'testing' });
    try {
      const r = await testLlmConnection({ provider: 'ollama', url, model });
      setTestResult(r.ok ? { state: 'ok', latency_ms: r.latency_ms } : { state: 'error', error: r.error });
    } catch (e: any) {
      setTestResult({ state: 'error', error: e?.message || 'Request failed' });
    }
  };

  const save = async () => {
    setSaving(true); setSaveMsg(null);
    try {
      await updateLlmConfig({ provider: 'ollama', url, model });
      setSaveMsg({ type: 'success', text: 'Ollama config saved.' });
    } catch (e: any) {
      setSaveMsg({ type: 'error', text: e?.message || 'Save failed.' });
    } finally { setSaving(false); }
  };

  return (
    <div className="space-y-5">
      <Field label="Server URL" hint="Default port 11434.">
        <TextInput value={url} onChange={e => setUrl(e.target.value)} placeholder="http://localhost:11434" />
      </Field>
      <Field label="Model Name">
        <TextInput value={model} onChange={e => setModel(e.target.value)} placeholder="llama3" />
      </Field>
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" onClick={fetchModels} isLoading={fetching}>
          <i className="fas fa-download mr-2"></i>Fetch Available Models
        </Button>
        {fetchError && <span className="text-xs text-rose-500">{fetchError}</span>}
      </div>
      {fetchedModels.length > 0 && (
        <Field label="Available Models">
          <Select value={model} onChange={e => setModel(e.target.value)}>
            {fetchedModels.map(m => <option key={m} value={m}>{m}</option>)}
          </Select>
        </Field>
      )}
      <div className="flex flex-wrap items-center gap-3 pt-1">
        <Button variant="secondary" onClick={runTest} disabled={testResult.state === 'testing'}>
          <i className="fas fa-plug mr-2"></i>Test Connection
        </Button>
        <ConnectionBadge result={testResult} />
      </div>
      {saveMsg && <p className={`text-sm font-medium ${saveMsg.type === 'success' ? 'text-emerald-600' : 'text-rose-500'}`}>{saveMsg.text}</p>}
      <Button onClick={save} isLoading={saving} className="w-fit">
        <i className="fas fa-save mr-2"></i>Save Ollama Config
      </Button>
    </div>
  );
};

// ── Main SettingsView ────────────────────────────────────────────────────────
const SettingsView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Provider>('lm_studio');
  const [cfg, setCfg] = useState<any>(null);

  useEffect(() => {
    getConfig()
      .then((c: any) => setCfg(c))
      .catch(() => {/* use defaults */});
  }, []);

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in duration-500">
      <div className="space-y-6">
        <h2 className="text-xl font-bold text-slate-800">Workspace Settings</h2>

        {/* LLM Provider Card */}
        <Card title="LLM Provider">
          <div className="space-y-6">
            {/* Pill-style tab bar */}
            <div className="flex flex-wrap gap-2">
              {TABS.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-all duration-150 ${
                    activeTab === tab.id
                      ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Panel content */}
            {activeTab === 'lm_studio' && <LmStudioPanel initialCfg={cfg} />}
            {activeTab === 'openai' && (
              <ApiKeyPanel
                provider="openai"
                label="OpenAI"
                models={['gpt-4o', 'gpt-4-turbo', 'gpt-3.5-turbo']}
                initialKey={cfg?.api_keys?.openai || ''}
                initialModel={cfg?.openai?.model}
              />
            )}
            {activeTab === 'gemini' && (
              <ApiKeyPanel
                provider="gemini"
                label="Gemini"
                models={['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash']}
                initialKey={cfg?.api_keys?.gemini || ''}
                initialModel={cfg?.gemini?.model}
              />
            )}
            {activeTab === 'anthropic' && (
              <ApiKeyPanel
                provider="anthropic"
                label="Anthropic"
                models={['claude-3-5-sonnet-20241022', 'claude-3-haiku-20240307', 'claude-3-opus-20240229']}
                initialKey={cfg?.api_keys?.anthropic || ''}
                initialModel={cfg?.anthropic?.model}
              />
            )}
            {activeTab === 'ollama' && <OllamaPanel initialCfg={cfg} />}
          </div>
        </Card>

        {/* MCP Server Connections — unchanged */}
        <Card title="MCP Server Connections">
          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 border border-emerald-100 bg-emerald-50 rounded-xl">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-emerald-500 flex items-center justify-center text-white">
                  <i className="fas fa-server"></i>
                </div>
                <div>
                  <p className="font-bold text-slate-800">Production MCP-1</p>
                  <p className="text-xs text-emerald-600">Connected • Stable</p>
                </div>
              </div>
              <Button variant="ghost" className="text-rose-500 hover:bg-rose-50">Disconnect</Button>
            </div>
            <Button variant="ghost" className="w-full border-2 border-dashed border-slate-200 hover:border-indigo-300 hover:text-indigo-600">
              <i className="fas fa-plus mr-2"></i> Add New Server
            </Button>
          </div>
        </Card>

        {/* Preferences — unchanged */}
        <Card title="Preferences">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-bold text-slate-800">Auto-save Workflows</p>
                <p className="text-xs text-slate-500">Automatically save changes every 30 seconds.</p>
              </div>
              <div className="w-12 h-6 bg-indigo-600 rounded-full relative cursor-pointer">
                <div className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full"></div>
              </div>
            </div>
            <div className="flex items-center justify-between pt-4 border-t border-slate-100">
              <div>
                <p className="font-bold text-slate-800">Logging Level</p>
                <p className="text-xs text-slate-500">Determine how much detail to show in execution monitor.</p>
              </div>
              <select className="bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-sm">
                <option>Info</option>
                <option>Debug</option>
                <option>Verbose</option>
              </select>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default SettingsView;

