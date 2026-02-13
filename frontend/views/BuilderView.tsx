

import React, { useState } from 'react';
import { Card, Button } from '../components/Shared';
import { useWorkflowBuilder } from '../hooks/useWorkflowBuilder';
import { WorkflowConfig } from '../types';
import { englishToJsonSubmit, customizeJsonLLMSubmit } from '../api';


const BuilderView: React.FC = () => {
  const [step, setStep] = useState(1);
  const [instructions, setInstructions] = useState('');
  const [customInstructions, setCustomInstructions] = useState('');
  const [workflowConfig, setWorkflowConfig] = useState<WorkflowConfig | null>(null);
  const [customizedConfig, setCustomizedConfig] = useState<WorkflowConfig | null>(null);
  const [showResult, setShowResult] = useState(false);
  const [manualPrompt, setManualPrompt] = useState<string | null>(null);
  const [manualNote, setManualNote] = useState<string | null>(null);
  const [manualLLMResponse, setManualLLMResponse] = useState<string>('');
  const [manualMode, setManualMode] = useState<'translate'|'customize'|null>(null);
  const {
    loading, error, success, runId, status,
    handleSave, handleTranslate, handleCustomize, handleOrchestrate, pollStatus
  } = useWorkflowBuilder();

  // Poll for status if runId changes
  React.useEffect(() => {
    let interval: NodeJS.Timeout;
    if (runId) {
      interval = setInterval(() => pollStatus(runId), 2000);
    }
    return () => clearInterval(interval);
  }, [runId]);

  return (
    <div className="space-y-6 animate-in zoom-in-95 duration-300">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold ${step >= 1 ? 'bg-indigo-600 text-white' : 'bg-slate-200 text-slate-500'}`}>1</div>
          <div className="w-8 h-[2px] bg-slate-200"></div>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold ${step >= 2 ? 'bg-indigo-600 text-white' : 'bg-slate-200 text-slate-500'}`}>2</div>
          <div className="w-8 h-[2px] bg-slate-200"></div>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold ${step >= 3 ? 'bg-indigo-600 text-white' : 'bg-slate-200 text-slate-500'}`}>3</div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            className="text-sm"
            onClick={async () => {
              if (instructions) {
                const config = await handleTranslate(instructions);
                if (config) {
                  if ((config as any).manual) {
                    setManualPrompt((config as any).prompt);
                    setManualNote((config as any).note);
                    setWorkflowConfig(null);
                  } else {
                    setWorkflowConfig(config as any);
                    setManualPrompt(null);
                    setManualNote(null);
                  }
                }
              }
            }}
            disabled={loading || !instructions}
          >
            Validate
          </Button>
          <Button
            variant="primary"
            className="text-sm"
            onClick={async () => {
              if (workflowConfig) {
                await handleSave({ name: workflowConfig.graph_name, example: workflowConfig });
              }
            }}
            disabled={loading || !workflowConfig}
          >
            Save Workflow
          </Button>
          <Button
            variant="primary"
            className="text-sm"
            onClick={async () => {
              if (customizedConfig || workflowConfig) {
                const run_id = await handleOrchestrate(customizedConfig || workflowConfig!);
                if (run_id) setShowResult(true);
              }
            }}
            disabled={loading || !(customizedConfig || workflowConfig)}
          >
            Run
          </Button>
        </div>
      </div>

      <div className="flex flex-col md:flex-row gap-6">
        <div className="flex-1 space-y-4">
          <Card title="Instructions (English)">
            <textarea
              className="w-full p-2 border border-slate-200 rounded"
              rows={3}
              placeholder="Describe your workflow in English..."
              value={instructions}
              onChange={e => setInstructions(e.target.value)}
              disabled={loading}
            />
          </Card>
          <Card title="Customization (Optional)">
            <textarea
              className="w-full p-2 border border-slate-200 rounded"
              rows={2}
              placeholder="Add customization instructions..."
              value={customInstructions}
              onChange={e => setCustomInstructions(e.target.value)}
              disabled={loading || !workflowConfig}
            />
            <Button
              variant="secondary"
              className="mt-2"
              onClick={async () => {
                if (workflowConfig && customInstructions) {
                  const custom = await handleCustomize(workflowConfig, customInstructions);
                  if (custom) {
                    if ((custom as any).manual) {
                      setManualPrompt((custom as any).prompt);
                      setManualNote((custom as any).note);
                      setManualMode('customize');
                    } else {
                      setCustomizedConfig(custom as any);
                    }
                  }
                }
              }}
              disabled={loading || !workflowConfig || !customInstructions}
            >
              Apply Customization
            </Button>
          </Card>

          {manualPrompt && (
            <Card title="Manual LLM Prompt (Copy & Paste)">
              <div className="space-y-2">
                <textarea readOnly className="w-full p-2 border border-slate-200 rounded h-36" value={manualPrompt} />
                {manualNote && <div className="text-sm text-slate-500">{manualNote}</div>}
                <div>
                  <label className="block text-sm mb-1">Paste LLM output (JSON only):</label>
                  <textarea className="w-full p-2 border border-slate-200 rounded h-36" value={manualLLMResponse} onChange={e => setManualLLMResponse(e.target.value)} />
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="primary"
                    onClick={async () => {
                      try {
                        if (manualMode === 'translate') {
                          const res = await englishToJsonSubmit(instructions, manualLLMResponse);
                          if (res && res.config_json) {
                            setWorkflowConfig(res.config_json as any);
                            setManualPrompt(null);
                            setManualNote(null);
                            setManualLLMResponse('');
                            setManualMode(null);
                          }
                        } else if (manualMode === 'customize') {
                          const res = await customizeJsonLLMSubmit(workflowConfig, manualLLMResponse);
                          if (res && res.customized_json) {
                            setCustomizedConfig(res.customized_json as any);
                            setManualPrompt(null);
                            setManualNote(null);
                            setManualLLMResponse('');
                            setManualMode(null);
                          }
                        }
                      } catch (err) {
                        console.error(err);
                      }
                    }}
                    disabled={!manualLLMResponse}
                  >
                    Submit LLM Response
                  </Button>
                </div>
              </div>
            </Card>
          )}
          {error && <div className="text-red-500 text-sm">{error}</div>}
          {success && <div className="text-green-600 text-sm">{success}</div>}
        </div>
        <div className="flex-1 space-y-4">
          <Card title="Workflow JSON">
            <pre className="text-xs bg-slate-50 p-2 rounded overflow-x-auto h-48">
              {JSON.stringify(customizedConfig || workflowConfig, null, 2) || 'No workflow generated yet.'}
            </pre>
          </Card>
          {showResult && status && (
            <Card title="Execution Status & Result">
              <div className="mb-2">
                <span className="font-bold">Status:</span> {status.status}
              </div>
              {status.result && (
                <pre className="text-xs bg-slate-50 p-2 rounded overflow-x-auto max-h-40">
                  {JSON.stringify(status.result, null, 2)}
                </pre>
              )}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
};

export default BuilderView;
