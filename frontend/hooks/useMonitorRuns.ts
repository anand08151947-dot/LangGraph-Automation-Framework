import { useState } from 'react';
import { getWorkflowRuns, getWorkflowRun } from '../api.runs';
import { WorkflowRun } from '../types';

export function useMonitorRuns() {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<WorkflowRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load all runs
  const loadRuns = async () => {
    setLoading(true); setError(null);
    try {
      const data = await getWorkflowRuns();
      setRuns(data);
      if (data.length > 0) setSelectedRun(data[0]);
    } catch (e: any) {
      setError(e?.message || 'Failed to load runs');
    } finally {
      setLoading(false);
    }
  };

  // Select a run and fetch details/logs
  const selectRun = async (run_id: string) => {
    setLoading(true); setError(null);
    try {
      const run = await getWorkflowRun(run_id);
      setSelectedRun(run);
    } catch (e: any) {
      setError(e?.message || 'Failed to load run details');
    } finally {
      setLoading(false);
    }
  };

  return { runs, selectedRun, loading, error, loadRuns, selectRun };
}
