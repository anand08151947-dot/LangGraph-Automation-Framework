
import React, { useState } from 'react';
import { Card, Button } from '../components/Shared';

const SettingsView: React.FC = () => {
  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in duration-500">
      <div className="space-y-6">
        <h2 className="text-xl font-bold text-slate-800">Workspace Settings</h2>
        
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
