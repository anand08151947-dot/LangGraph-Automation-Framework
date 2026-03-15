import { WorkflowRun } from '../types';
import api from './api';

// Fetch all workflow runs
export const getWorkflowRuns = async (): Promise<WorkflowRun[]> => {
  const res = await api.get<WorkflowRun[]>('/runs');
  return res.data;
};

// Fetch a single workflow run by ID (for logs/details)
export const getWorkflowRun = async (run_id: string): Promise<WorkflowRun> => {
  const res = await api.get<WorkflowRun>(`/run/${run_id}`);
  return res.data;
};

// FE-MON-1: Cancel a running workflow
export const cancelRun = async (run_id: string): Promise<{ status: string }> => {
  const res = await api.post<{ status: string }>(`/runs/${run_id}/cancel`);
  return res.data;
};

// FE-MON-1: Rerun a workflow using its stored config
export const rerunWorkflow = async (config_json: any): Promise<{ run_id: string; status: string }> => {
  const res = await api.post<{ run_id: string; status: string }>('/orchestrate_async', { config_json });
  return res.data;
};

// FE-MON-6: Fetch the config used for a specific run
export const getRunConfig = async (run_id: string): Promise<{ run_id: string; config: any; template?: string }> => {
  const res = await api.get(`/runs/${run_id}/config`);
  return res.data;
};

// MEM-6: Fetch STM for a session
export const getStm = async (session_id: string): Promise<{ session_id: string; stm: any }> => {
  const res = await api.get(`/memory/stm/${session_id}`);
  return res.data;
};

// MEM-6: Fetch LTM for a session
export const getLtm = async (session_id: string): Promise<{ session_id: string; ltm: any[] }> => {
  const res = await api.get(`/memory/ltm/${session_id}`);
  return res.data;
};
