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
