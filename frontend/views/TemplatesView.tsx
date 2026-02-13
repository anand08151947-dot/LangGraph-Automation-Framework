

import React, { useState } from 'react';
import { Card, Button, Badge } from '../components/Shared';
import { useTemplates } from '../hooks/useTemplates';

const TemplatesView: React.FC = () => {

  const [searchTerm, setSearchTerm] = useState('');
  const [selectedDomain, setSelectedDomain] = useState('All');
  const { data: templates, loading, error } = useTemplates();

  const domains = ['All', ...Array.from(new Set(templates.map(t => t.description || 'Other')))]

  const filtered = templates.filter(t =>
    (selectedDomain === 'All' || t.description === selectedDomain) &&
    (t.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (t.description || '').toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return (
    <div className="space-y-6 animate-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div className="relative flex-1 w-full max-w-md">
          <i className="fas fa-search absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"></i>
          <input 
            type="text" 
            placeholder="Search templates..."
            className="w-full pl-10 pr-4 py-2 bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div className="flex gap-2 overflow-x-auto w-full md:w-auto pb-2 md:pb-0">
          {domains.map(domain => (
            <button
              key={domain}
              onClick={() => setSelectedDomain(domain)}
              className={`px-4 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
                selectedDomain === domain ? 'bg-indigo-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
              }`}
            >
              {domain}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="text-center py-20 bg-white rounded-2xl border border-slate-300">
          <span className="text-slate-400">Loading templates...</span>
        </div>
      )}

      {error && (
        <div className="text-center py-20 bg-white rounded-2xl border border-red-300">
          <span className="text-red-500">{error}</span>
        </div>
      )}

      {!loading && !error && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filtered.map(template => (
            <Card key={template.name} className="flex flex-col h-full hover:shadow-md transition-shadow group">
              <div className="flex-1 space-y-4">
                <div className="flex justify-between items-start">
                  <div className="p-3 bg-indigo-50 rounded-xl text-indigo-600 group-hover:scale-110 transition-transform">
                    <i className="fas fa-file-code text-xl"></i>
                  </div>
                  <Badge type="INFO" label={template.description || 'Other'} />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-800">{template.name}</h3>
                  <p className="text-sm text-slate-500 mt-1 line-clamp-2">{template.description}</p>
                </div>
                <div className="p-3 bg-slate-50 rounded-lg">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Example Config</p>
                  <pre className="text-xs text-slate-600 overflow-hidden text-ellipsis">
                    {JSON.stringify(template.example, null, 2).substring(0, 100)}...
                  </pre>
                </div>
              </div>
              <div className="mt-6 flex gap-3">
                <Button variant="primary" className="flex-1 text-sm">Use Template</Button>
                <Button variant="secondary" className="flex-1 text-sm">Customize</Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {!loading && !error && filtered.length === 0 && (
        <div className="text-center py-20 bg-white rounded-2xl border border-dashed border-slate-300">
          <div className="text-slate-300 mb-4">
            <i className="fas fa-folder-open text-6xl"></i>
          </div>
          <h3 className="text-xl font-semibold text-slate-800">No templates found</h3>
          <p className="text-slate-500">Try adjusting your filters or search terms.</p>
        </div>
      )}
    </div>
  );
};

export default TemplatesView;
