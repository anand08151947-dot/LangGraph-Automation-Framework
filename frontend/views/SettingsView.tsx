
import React, { useState, useEffect } from 'react';
import { Card, Button } from '../components/Shared';
import { getConfig, updateLmStudioConfig } from '../services/api';

const SettingsView: React.FC = () => {
  const [lmStudioUrl, setLmStudioUrl] = useState('http://localhost:1234/v1/completions');
  const [lmStudioModel, setLmStudioModel] = useState('local-model');
  const [saveMsg, setSaveMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getConfig()
      .then((cfg: any) => {
        if (cfg?.lm_studio?.url) setLmStudioUrl(cfg.lm_studio.url);
        if (cfg?.lm_studio?.model) setLmStudioModel(cfg.lm_studio.model);
      })
      .catch(() => {/* use defaults */});
  }, []);

  const handleSaveLmStudio = async () => {
    setSaving(true); setSaveMsg(null);
    try {
      await updateLmStudioConfig(lmStudioUrl, lmStudioModel);
      setSaveMsg({ type: 'success', text: 'LM Studio config saved successfully.' });
    } catch (e: any) {
      setSaveMsg({ type: 'error', text: e?.message || 'Failed to save config.' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in duration-500">
      <div className="space-y-6">
        <h2 className="text-xl font-bold text-slate-800">Workspace Settings</h2>

        <Card title="LM Studio (Local LLM)">
          <div className="space-y-6">
            <div className="flex items-center gap-3 p-3 border border-indigo-100 bg-indigo-50 rounded-xl">
              <div className="w-10 h-10 rounded-lg bg-indigo-600 flex items-center justify-center text-white flex-shrink-0">
                <i className="fas fa-robot"></i>
              </div>
              <div>
                <p className="font-bold text-slate-800 text-sm">LM Studio</p>
                <p className="text-xs text-indigo-600">Active LLM provider — runs locally on your machine</p>
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Server URL</label>
              <input
                type="text"
                className="w-full pl-4 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-lg font-mono text-sm focus:ring-2 focus:ring-indigo-500/20 outline-none"
                value={lmStudioUrl}
                onChange={(e) => setLmStudioUrl(e.target.value)}
                placeholder="http://localhost:1234/v1/completions"
              />
              <p className="text-xs text-slate-400">LM Studio completions endpoint (default port 1234).</p>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Model Name</label>
              <input
                type="text"
                className="w-full pl-4 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-lg font-mono text-sm focus:ring-2 focus:ring-indigo-500/20 outline-none"
                value={lmStudioModel}
                onChange={(e) => setLmStudioModel(e.target.value)}
                placeholder="local-model"
              />
              <p className="text-xs text-slate-400">Must match the model identifier shown in LM Studio.</p>
            </div>
            {saveMsg && (
              <p className={`text-sm font-medium ${saveMsg.type === 'success' ? 'text-emerald-600' : 'text-rose-500'}`}>{saveMsg.text}</p>
            )}
            <Button onClick={handleSaveLmStudio} isLoading={saving} className="w-fit">
              Save LM Studio Config
            </Button>
          </div>
        </Card>

        <Card title="API Keys">
          <div className="space-y-6">
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Gemini API Key</label>
              <div className="relative">
                <input 
                  type="password" 
                  className="w-full pl-4 pr-12 py-3 bg-slate-50 border border-slate-200 rounded-lg font-mono text-sm focus:ring-2 focus:ring-indigo-500/20 outline-none"
                  value="••••••••••••••••••••••••••••"
                  readOnly
                />
                <button className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-indigo-600">
                  <i className="fas fa-eye"></i>
                </button>
              </div>
              <p className="text-xs text-slate-400">Used for translation and AI refinement services.</p>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">OpenAI API Key</label>
              <div className="relative">
                <input 
                  type="password" 
                  className="w-full pl-4 pr-12 py-3 bg-slate-50 border border-slate-200 rounded-lg font-mono text-sm focus:ring-2 focus:ring-indigo-500/20 outline-none"
                  placeholder="sk-..."
                />
              </div>
            </div>

            <Button variant="secondary" className="w-fit">Save Changes</Button>
          </div>
        </Card>

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
