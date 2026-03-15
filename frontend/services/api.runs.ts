import { WorkflowRun } from '../types';
import api from './api';

// Fetch workflow runs with optional pagination (API-4)
export const getWorkflowRuns = async (page = 1, limit = 20): Promise<WorkflowRun[]> => {
  const res = await api.get<any>(`/runs?page=${page}&limit=${limit}`);
  // Support both legacy array response and new paginated { items: [] } response
  const data = res.data;
  return Array.isArray(data) ? data : (data.items ?? []);
};

// FE-MON-2: Fetch approval checkpoint info
export const getApprovalStatus = async (run_id: string): Promise<{
  run_id: string; status: string; checkpoint_node?: string; state_snapshot?: any
}> => {
  const res = await api.get(`/approval/${run_id}`);
  return res.data;
};

// FE-MON-2: Submit approval/resume for a run awaiting human approval
export const submitApproval = async (run_id: string, approval_input: Record<string, any>): Promise<any> => {
  const res = await api.post(`/resume/${run_id}`, { approval_input });
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
