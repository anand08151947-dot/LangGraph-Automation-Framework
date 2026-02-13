

import React, { useEffect, useState } from 'react';
import { Card, Button } from '../components/Shared';
import { useExportArtifacts } from '../hooks/useExportArtifacts';


const ExportView: React.FC = () => {
  const [selected, setSelected] = useState<string[]>([]);
  const { artifacts, loading, error, loadArtifacts, exportBundle } = useExportArtifacts();
  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    loadArtifacts();
  }, []);

  const toggleSelect = (id: string) => {
    setSelected(prev => prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]);
  };

  const handleExport = async () => {
    if (selected.length === 0) return;
    setIsExporting(true);
    await exportBundle(selected);
    setIsExporting(false);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in duration-500">
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold text-slate-800">Export Your Workflow Bundle</h1>
        <p className="text-slate-500">Select the components you want to include in your package.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        <div className="md:col-span-2 space-y-4">
          <Card title="Artifact Selection">
            <div className="divide-y divide-slate-100">
              {loading ? (
                <div className="p-4 text-center text-slate-400">Loading artifacts...</div>
              ) : error ? (
                <div className="p-4 text-center text-rose-400">{error}</div>
              ) : artifacts.length === 0 ? (
                <div className="p-4 text-center text-slate-400">No artifacts available.</div>
              ) : (
                artifacts.map(artifact => (
                  <div
                    key={artifact.id}
                    className={`flex items-center justify-between p-4 cursor-pointer transition-colors ${selected.includes(artifact.id) ? 'bg-indigo-50/50' : 'hover:bg-slate-50'}`}
                    onClick={() => toggleSelect(artifact.id)}
                  >
                    <div className="flex items-center gap-4">
                      <input
                        type="checkbox"
                        className="w-5 h-5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                        checked={selected.includes(artifact.id)}
                        readOnly
                      />
                      <div>
                        <p className="font-bold text-slate-800">{artifact.name}</p>
                        <p className="text-xs text-slate-400 font-medium uppercase">{artifact.type} • {artifact.size}</p>
                      </div>
                    </div>
                    <div className="text-slate-400">
                      <i className={`fas ${artifact.type === 'code' ? 'fa-code' : artifact.type === 'json' ? 'fa-brackets-curly' : 'fa-file'}`}></i>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Bundle Summary">
            <div className="space-y-4">
              <div className="flex justify-between text-sm">
                <span className="text-slate-500">Items Selected</span>
                <span className="font-bold">{selected.length}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-500">Estimated Size</span>
                <span className="font-bold">~67 KB</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-500">Format</span>
                <span className="font-bold">ZIP / Tarball</span>
              </div>
              <div className="pt-4 border-t border-slate-100">
                <Button 
                  className="w-full h-12" 
                  disabled={selected.length === 0} 
                  isLoading={isExporting}
                  onClick={handleExport}
                >
                  <i className="fas fa-file-archive mr-2"></i> Download Bundle
                </Button>
              </div>
            </div>
          </Card>

          <Card className="bg-slate-50 border-dashed border-2 border-slate-200">
            <div className="flex flex-col items-center text-center p-4">
              <div className="w-12 h-12 rounded-full bg-slate-200 flex items-center justify-center text-slate-500 mb-4">
                <i className="fab fa-github text-xl"></i>
              </div>
              <h4 className="font-bold text-slate-800 mb-1">Push to GitHub</h4>
              <p className="text-xs text-slate-500 mb-4">Directly push artifacts to your repository (Coming Soon).</p>
              <Button variant="ghost" className="w-full text-xs" disabled>Connect GitHub</Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default ExportView;
