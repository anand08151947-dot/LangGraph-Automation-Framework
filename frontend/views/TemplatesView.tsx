import React, { useState, useMemo } from 'react';
import { useTemplates } from '../hooks/useTemplates';
import { TemplateInfo } from '../types';

const CATEGORY_META: Record<string, { label: string; icon: string; color: string; bg: string }> = {
  'General':    { label: 'General',    icon: 'fa-layer-group',  color: 'text-indigo-600', bg: 'bg-indigo-50'   },
  'Advanced':   { label: 'Advanced',   icon: 'fa-bolt',         color: 'text-violet-600', bg: 'bg-violet-50'   },
  'Areas':      { label: 'Areas',      icon: 'fa-map',          color: 'text-sky-600',    bg: 'bg-sky-50'      },
  'Domains':    { label: 'Domains',    icon: 'fa-cubes',        color: 'text-teal-600',   bg: 'bg-teal-50'     },
  'Expert':     { label: 'Expert',     icon: 'fa-star',         color: 'text-amber-600',  bg: 'bg-amber-50'    },
  'Industries': { label: 'Industries', icon: 'fa-industry',     color: 'text-orange-600', bg: 'bg-orange-50'   },
  'Sectors':    { label: 'Sectors',    icon: 'fa-chart-pie',    color: 'text-rose-600',   bg: 'bg-rose-50'     },
  'Verticals':  { label: 'Verticals',  icon: 'fa-sitemap',      color: 'text-emerald-600',bg: 'bg-emerald-50'  },
};

const FILE_TO_CAT: Record<string, string> = {
  'prompt_templates.json':            'General',
  'prompt_templates_advanced.json':   'Advanced',
  'prompt_templates_areas.json':      'Areas',
  'prompt_templates_domains.json':    'Domains',
  'prompt_templates_expert.json':     'Expert',
  'prompt_templates_industries.json': 'Industries',
  'prompt_templates_sectors.json':    'Sectors',
  'prompt_templates_verticals.json':  'Verticals',
};

function getCategory(t: TemplateInfo): string {
  return FILE_TO_CAT[t.source_file || ''] || 'General';
}

type SortOption = 'name' | 'category';

const TemplateCard: React.FC<{
  template: TemplateInfo;
  onUse: () => void;
  onCustomize: () => void;
}> = ({ template, onUse, onCustomize }) => {
  const [expanded, setExpanded] = useState(false);
  const cat = getCategory(template);
  const meta = CATEGORY_META[cat] || CATEGORY_META['General'];
  const agentCount = (template.example as any)?.agents?.length ?? 0;

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 flex flex-col">
      <div className="p-5 flex items-start gap-4">
        <div className={`w-11 h-11 rounded-xl ${meta.bg} flex items-center justify-center flex-shrink-0`}>
          <i className={`fas ${meta.icon} ${meta.color}`}></i>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-bold text-slate-800 text-sm leading-snug">{template.name}</h3>
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider flex-shrink-0 ${meta.bg} ${meta.color}`}>
              {cat}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1 line-clamp-2">{template.description}</p>
        </div>
      </div>

      {agentCount > 0 && (
        <div className="px-5 flex gap-4 text-xs text-slate-400 font-medium">
          <span><i className="fas fa-robot mr-1"></i>{agentCount} agent{agentCount !== 1 ? 's' : ''}</span>
          {(template.example as any)?.graph_name && (
            <span className="font-mono truncate text-slate-300">{(template.example as any).graph_name}</span>
          )}
        </div>
      )}

      {template.sample_prompt && (
        <div className="mx-5 mt-3 p-3 bg-amber-50 border border-amber-100 rounded-xl">
          <p className="text-[10px] font-bold text-amber-700 uppercase tracking-widest mb-1">
            <i className="fas fa-comment-dots mr-1"></i>Sample Prompt
          </p>
          <p className={`text-xs text-slate-600 ${expanded ? '' : 'line-clamp-2'}`}>{template.sample_prompt}</p>
          {template.sample_prompt.length > 120 && (
            <button className="text-[10px] text-amber-600 font-semibold mt-1 hover:underline" onClick={() => setExpanded(e => !e)}>
              {expanded ? 'Show less' : 'Show more'}
            </button>
          )}
        </div>
      )}

      {template.example && (
        <details className="mx-5 mt-3 group">
          <summary className="text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-600 flex items-center gap-1">
            <i className="fas fa-code text-[9px] group-open:rotate-90 transition-transform"></i> Workflow Config
          </summary>
          <pre className="mt-2 p-3 bg-slate-900 text-emerald-300 text-[10px] font-mono rounded-xl overflow-x-auto max-h-36 overflow-y-auto">
            {JSON.stringify(template.example, null, 2)}
          </pre>
        </details>
      )}

      <div className="mt-auto p-5 pt-4 flex gap-3">
        <button onClick={onUse}
          className="flex-1 py-2 px-3 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold transition-colors flex items-center justify-center gap-1.5 active:scale-95">
          <i className="fas fa-play"></i> Use Template
        </button>
        <button onClick={onCustomize}
          className="flex-1 py-2 px-3 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold transition-colors flex items-center justify-center gap-1.5 active:scale-95">
          <i className="fas fa-sliders-h"></i> Customize
        </button>
      </div>
    </div>
  );
};

const TemplatesView: React.FC<{ onNavigate?: (view: string, data?: any) => void }> = ({ onNavigate }) => {
  const [search, setSearch] = useState('');
  const [selectedCat, setSelectedCat] = useState('All');
  const [sort, setSort] = useState<SortOption>('category');
  const { data: templates, loading, error } = useTemplates();

  const catCounts = useMemo(() => {
    const counts: Record<string, number> = { All: templates.length };
    templates.forEach(t => {
      const c = getCategory(t);
      counts[c] = (counts[c] || 0) + 1;
    });
    return counts;
  }, [templates]);

  const categories = ['All', ...Object.keys(CATEGORY_META)];

  const filtered = useMemo(() => {
    const term = search.toLowerCase();
    return templates
      .filter(t => {
        const matchCat = selectedCat === 'All' || getCategory(t) === selectedCat;
        const matchSearch = !term ||
          t.name.toLowerCase().includes(term) ||
          (t.description || '').toLowerCase().includes(term) ||
          (t.sample_prompt || '').toLowerCase().includes(term);
        return matchCat && matchSearch;
      })
      .sort((a, b) => sort === 'name'
        ? a.name.localeCompare(b.name)
        : getCategory(a).localeCompare(getCategory(b)) || a.name.localeCompare(b.name));
  }, [templates, search, selectedCat, sort]);

  return (
    <div className="flex gap-6 animate-in fade-in duration-300">
      {/* Sidebar */}
      <aside className="w-52 flex-shrink-0 space-y-1">
        <h2 className="text-xs font-bold text-slate-400 uppercase tracking-widest px-3 mb-3">Categories</h2>
        {categories.map(cat => {
          const meta = CATEGORY_META[cat];
          const count = catCounts[cat] || 0;
          const active = selectedCat === cat;
          return (
            <button key={cat} onClick={() => setSelectedCat(cat)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                active ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200' : 'text-slate-600 hover:bg-slate-100'}`}>
              <i className={`fas ${meta ? meta.icon : 'fa-th-large'} w-4 text-center ${active ? 'text-white' : (meta ? meta.color : 'text-slate-400')}`}></i>
              <span className="flex-1 text-left">{cat}</span>
              <span className={`text-xs px-1.5 py-0.5 rounded-full font-bold ${active ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-500'}`}>{count}</span>
            </button>
          );
        })}
      </aside>

      {/* Main */}
      <div className="flex-1 min-w-0 space-y-5">
        {/* Toolbar */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <i className="fas fa-search absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-sm"></i>
            <input type="text" placeholder="Search by name, description, or prompt…" value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-9 pr-8 py-2.5 bg-white border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all" />
            {search && (
              <button onClick={() => setSearch('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                <i className="fas fa-times text-xs"></i>
              </button>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <span className="text-xs text-slate-400 font-medium">Sort:</span>
            <select value={sort} onChange={e => setSort(e.target.value as SortOption)}
              className="py-2.5 px-3 bg-white border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500">
              <option value="category">By Category</option>
              <option value="name">By Name (A–Z)</option>
            </select>
          </div>
        </div>

        {/* Results count */}
        {!loading && !error && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-500">
              {filtered.length === templates.length ? `${templates.length} templates` : `${filtered.length} of ${templates.length} templates`}
            </span>
            {(search || selectedCat !== 'All') && (
              <button onClick={() => { setSearch(''); setSelectedCat('All'); }} className="text-xs text-indigo-600 hover:underline font-medium">
                Clear filters
              </button>
            )}
          </div>
        )}

        {/* Loading skeletons */}
        {loading && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-64 bg-slate-100 rounded-2xl animate-pulse" />
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex flex-col items-center py-20 text-center">
            <div className="w-16 h-16 bg-rose-50 rounded-full flex items-center justify-center mb-4">
              <i className="fas fa-exclamation-triangle text-rose-400 text-2xl"></i>
            </div>
            <h3 className="text-lg font-semibold text-slate-800 mb-1">Failed to load templates</h3>
            <p className="text-sm text-slate-500">{error}</p>
          </div>
        )}

        {/* Empty */}
        {!loading && !error && filtered.length === 0 && (
          <div className="flex flex-col items-center py-20 text-center">
            <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mb-4">
              <i className="fas fa-search text-slate-400 text-2xl"></i>
            </div>
            <h3 className="text-lg font-semibold text-slate-800 mb-1">No templates found</h3>
            <p className="text-sm text-slate-500">Try a different search or select a different category.</p>
            <button onClick={() => { setSearch(''); setSelectedCat('All'); }} className="mt-4 text-sm text-indigo-600 hover:underline font-medium">
              Clear filters
            </button>
          </div>
        )}

        {/* Grid */}
        {!loading && !error && filtered.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {filtered.map(template => (
              <TemplateCard key={template.name} template={template}
                onUse={() => onNavigate?.('/builder', { template })}
                onCustomize={() => onNavigate?.('/translation', { template })} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default TemplatesView;
