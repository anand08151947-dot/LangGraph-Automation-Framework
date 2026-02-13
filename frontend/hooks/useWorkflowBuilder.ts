import { useState } from 'react';
import {
  saveTemplate,
  englishToJson,
  customizeJsonLLM,
  orchestrateAsync,
  getStatus
} from '../api';
import {
  WorkflowConfig,
  SaveTemplateRequest,
  OrchestrationResponse,
  StatusResponse
} from '../types';

export function useWorkflowBuilder() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);

  // Save workflow config as template
  const handleSave = async (data: SaveTemplateRequest) => {
    setLoading(true); setError(null); setSuccess(null);
    try {
      const res = await saveTemplate(data);
      setSuccess(`Saved as ${res.filename}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Save failed');
    } finally {
      setLoading(false);
    }
  };

  // Translate English to JSON
  const handleTranslate = async (instructions: string) => {
    setLoading(true); setError(null); setSuccess(null);
    try {
      const res = await englishToJson(instructions);
      if (res.prompt) {
        // Manual adapter: return prompt and instruct caller to submit back the LLM response
        setSuccess('Manual LLM prompt generated');
        return { manual: true, prompt: res.prompt, note: res.note } as any;
      }
      setSuccess('Translation successful');
      return res.config_json as any;
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Translation failed');
      return null;
    } finally {
      setLoading(false);
    }
  };

  // Customize JSON with LLM
  const handleCustomize = async (base_json: WorkflowConfig, custom_instructions: string) => {
    setLoading(true); setError(null); setSuccess(null);
    try {
      const res = await customizeJsonLLM(base_json, custom_instructions);
      if (res.prompt) {
        setSuccess('Manual LLM prompt generated');
        return { manual: true, prompt: res.prompt, note: res.note } as any;
      }
      setSuccess('Customization successful');
      return res.customized_json as any;
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Customization failed');
      return null;
    } finally {
      setLoading(false);
    }
  };

  // Orchestrate workflow
  const handleOrchestrate = async (config_json: WorkflowConfig) => {
    setLoading(true); setError(null); setSuccess(null);
    try {
      const res: OrchestrationResponse = await orchestrateAsync(config_json);
      setRunId(res.run_id);
      setSuccess('Orchestration started');
      return res.run_id;
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Orchestration failed');
      return null;
    } finally {
      setLoading(false);
    }
  };

  // Poll for status
  const pollStatus = async (run_id: string) => {
    setLoading(true); setError(null);
    try {
      const res = await getStatus(run_id);
      setStatus(res);
      if (res.status === 'completed' || res.status === 'error') {
        setLoading(false);
      }
      return res;
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Status check failed');
      setLoading(false);
      return null;
    }
  };

  return {
    loading, error, success, runId, status,
    handleSave, handleTranslate, handleCustomize, handleOrchestrate, pollStatus
  };
}
