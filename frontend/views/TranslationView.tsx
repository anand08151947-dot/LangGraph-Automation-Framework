
import React, { useState } from 'react';
import { Card, Button } from '../components/Shared';
import { englishToJson, customizeJsonLLM } from '../services/api';

const TranslationView: React.FC = () => {
  const [instruction, setInstruction] = useState('');
  const [refinement, setRefinement] = useState('');
  const [generatedJson, setGeneratedJson] = useState('{\n  "status": "No workflow generated yet",\n  "description": "Describe your workflow in English on the left to get started."\n}');
  const [isTranslating, setIsTranslating] = useState(false);
  const [isRefining, setIsRefining] = useState(false);

  const handleTranslate = async () => {
    if (!instruction.trim()) return;
    setIsTranslating(true);
    try {
      const result = await englishToJson(instruction);
      setGeneratedJson(JSON.stringify(result.config_json ?? result, null, 2));
    } catch (e) {
      setGeneratedJson(JSON.stringify({ error: 'Translation failed. Is LM Studio running?' }, null, 2));
    }
    setIsTranslating(false);
  };

  const handleRefine = async () => {
    if (!refinement.trim()) return;
    setIsRefining(true);
    try {
      let base: any = {};
      try { base = JSON.parse(generatedJson); } catch { base = {}; }
      const result = await customizeJsonLLM(base, refinement);
      setGeneratedJson(JSON.stringify(result.customized_json ?? result, null, 2));
      setRefinement('');
    } catch (e) {
      setGeneratedJson(JSON.stringify({ error: 'Refinement failed. Is LM Studio running?' }, null, 2));
    }
    setIsRefining(false);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-in slide-in-from-left-4 duration-500">
      <div className="space-y-6">
        <Card title="English Instructions">
          <div className="space-y-4">
            <p className="text-sm text-slate-500">Describe the agents, tools, and the sequence of actions you want to orchestrate.</p>
            <textarea
              className="w-full h-48 p-4 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all font-medium text-slate-700"
              placeholder="e.g. Create a research agent that uses Google Search to find news about NVIDIA. Then send the summary to a writing agent that drafts a blog post. Finally, save the output as a Markdown file."
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
            />
            <Button 
              variant="primary" 
              className="w-full h-12" 
              onClick={handleTranslate} 
              isLoading={isTranslating}
            >
              <i className="fas fa-magic mr-2"></i> Translate to JSON Workflow
            </Button>
          </div>
        </Card>

        {generatedJson && !generatedJson.includes('No workflow generated yet') && (
          <Card title="Apply Refinements">
            <div className="space-y-4">
              <input
                type="text"
                className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                placeholder="e.g. Add a logic step to check for source reliability..."
                value={refinement}
                onChange={(e) => setRefinement(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleRefine()}
              />
              <Button 
                variant="secondary" 
                className="w-full" 
                onClick={handleRefine}
                isLoading={isRefining}
              >
                Apply Customization
              </Button>
            </div>
          </Card>
        )}
      </div>

      <div className="space-y-6">
        <Card title="Generated Workflow JSON" className="h-full flex flex-col">
          <div className="flex-1 min-h-[500px] relative group">
            <div className="absolute top-4 right-4 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <button className="p-2 bg-white border border-slate-200 rounded shadow-sm hover:bg-slate-50 text-slate-600" title="Copy to clipboard">
                <i className="fas fa-copy"></i>
              </button>
              <button className="p-2 bg-white border border-slate-200 rounded shadow-sm hover:bg-slate-50 text-slate-600" title="Download JSON">
                <i className="fas fa-download"></i>
              </button>
            </div>
            <textarea
              readOnly
              className="w-full h-full p-6 bg-slate-900 text-indigo-300 font-mono text-sm rounded-xl focus:outline-none overflow-auto"
              value={generatedJson}
            />
          </div>
          <div className="mt-4 pt-4 border-t border-slate-100 flex gap-3">
            <Button variant="ghost" className="flex-1">Discard</Button>
            <Button variant="primary" className="flex-1">Apply to Builder</Button>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default TranslationView;
