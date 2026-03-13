
import React, { useState, useEffect } from 'react';
import { Card, Button } from '../components/Shared';
import { englishToJson, customizeJsonLLM } from '../services/api';
import { TemplateInfo } from '../types';

const TranslationView: React.FC<{
  initialTemplate?: TemplateInfo | null;
  onNavigate?: (path: string, data?: any) => void;
}> = ({ initialTemplate, onNavigate }) => {
  const [instruction, setInstruction] = useState('');
  const [refinement, setRefinement] = useState('');
  const [generatedJson, setGeneratedJson] = useState('{\n  "status": "No workflow generated yet",\n  "description": "Describe your workflow in English on the left to get started."\n}');
  const [isTranslating, setIsTranslating] = useState(false);
  const [isRefining, setIsRefining] = useState(false);
  const [copyLabel, setCopyLabel] = useState('');

  // Pre-populate when coming from "Customize" on Templates page
  useEffect(() => {
    if (initialTemplate) {
      // Use sample_prompt as the starting instruction for refinement
      const prompt = initialTemplate.sample_prompt || initialTemplate.description || '';
      setInstruction(prompt ? `Customize this template — "${initialTemplate.name}":\n\n${prompt}` : `Customize template: ${initialTemplate.name}`);
      // Pre-load the template JSON into the output panel
      const templateJson = (initialTemplate.example as any) || {};
      setGeneratedJson(JSON.stringify(templateJson, null, 2));
    }
  }, [initialTemplate]);

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

  const handleCopy = () => {
    navigator.clipboard.writeText(generatedJson).then(() => {
      setCopyLabel('Copied!');
      setTimeout(() => setCopyLabel(''), 2000);
    });
  };

  const handleApplyToBuilder = () => {
    try {
      const cfg = JSON.parse(generatedJson);
      if (cfg && typeof cfg === 'object' && !cfg.error && !cfg.status) {
        onNavigate?.('/builder', {
          template: {
            name: cfg.graph_name || initialTemplate?.name || 'Custom Workflow',
            description: cfg.description || initialTemplate?.description || '',
            example: cfg,
          }
        });
      }
    } catch {
      alert('Cannot apply: Generated JSON is not a valid workflow config.');
    }
  };

  const hasJson = !generatedJson.includes('No workflow generated yet');

  return (
    <div className="space-y-4 animate-in slide-in-from-left-4 duration-500">
      {/* Template context banner */}
      {initialTemplate && (
        <div className="flex items-center gap-3 px-4 py-3 bg-indigo-50 border border-indigo-200 rounded-xl">
          <i className="fas fa-layer-group text-indigo-500"></i>
          <div className="flex-1 min-w-0">
            <span className="text-xs font-bold text-indigo-700 uppercase tracking-widest">Customizing template</span>
            <p className="text-sm font-semibold text-indigo-900 truncate">{initialTemplate.name}</p>
          </div>
          <button onClick={() => onNavigate?.('/templates')}
            className="text-xs text-indigo-600 hover:underline font-medium flex items-center gap-1">
            <i className="fas fa-arrow-left text-xs"></i> Back to Templates
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="space-y-6">
          <Card title={initialTemplate ? '✏️ Describe Your Changes' : 'English Instructions'}>
            <div className="space-y-4">
              <p className="text-sm text-slate-500">
                {initialTemplate
                  ? 'Describe how you want to customize this template. The LLM will generate an updated workflow config.'
                  : 'Describe the agents, tools, and the sequence of actions you want to orchestrate.'}
              </p>
              <textarea
                className="w-full h-48 p-4 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all font-medium text-slate-700"
                placeholder={initialTemplate
                  ? `e.g. Add a validation node after ${(initialTemplate.example as any)?.nodes?.[0]?.id || 'the first agent'}. Replace the web_search tool with a database lookup. Increase max_retries to 5.`
                  : 'e.g. Create a research agent that uses Google Search to find news about NVIDIA. Then send the summary to a writing agent that drafts a blog post.'}
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
              />
              <Button
                variant="primary"
                className="w-full h-12"
                onClick={handleTranslate}
                isLoading={isTranslating}
              >
                <i className="fas fa-magic mr-2"></i>
                {initialTemplate ? 'Regenerate from Description' : 'Translate to JSON Workflow'}
              </Button>
            </div>
          </Card>

          {/* Refinement panel — always visible when we have template JSON loaded */}
          {hasJson && (
            <Card title="🔧 Refine with Natural Language">
              <div className="space-y-4">
                <p className="text-sm text-slate-500">
                  Ask the LLM to tweak the current JSON — add nodes, change tools, adjust retry policies, etc.
                </p>
                <input
                  type="text"
                  className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                  placeholder="e.g. Add a summarisation node after the research step..."
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
                  <i className="fas fa-wand-magic-sparkles mr-2"></i> Apply Refinement
                </Button>
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          <Card title="Generated Workflow JSON" className="h-full flex flex-col">
            <div className="flex-1 min-h-[500px] relative group">
              <div className="absolute top-4 right-4 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                <button onClick={handleCopy}
                  className="px-3 py-1.5 bg-white border border-slate-200 rounded shadow-sm hover:bg-slate-50 text-slate-600 text-xs font-medium flex items-center gap-1"
                  title="Copy to clipboard">
                  <i className="fas fa-copy"></i> {copyLabel || 'Copy'}
                </button>
              </div>
              <textarea
                readOnly
                className="w-full h-full p-6 bg-slate-900 text-indigo-300 font-mono text-sm rounded-xl focus:outline-none overflow-auto"
                value={generatedJson}
              />
            </div>
            <div className="mt-4 pt-4 border-t border-slate-100 flex gap-3">
              <Button variant="ghost" className="flex-1"
                onClick={() => {
                  setGeneratedJson('{\n  "status": "No workflow generated yet",\n  "description": "Describe your workflow in English on the left to get started."\n}');
                  setInstruction('');
                }}>
                <i className="fas fa-trash-alt mr-1"></i> Discard
              </Button>
              <Button variant="primary" className="flex-1" onClick={handleApplyToBuilder}
                disabled={!hasJson}>
                <i className="fas fa-arrow-right mr-1"></i> Apply to Builder
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default TranslationView;
