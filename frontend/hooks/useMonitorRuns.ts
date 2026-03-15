import { useState, useEffect, useRef, useCallback } from 'react';
import { getWorkflowRuns, getWorkflowRun, cancelRun as apiCancelRun, rerunWorkflow } from '../services/api.runs';
import { WorkflowRun, WorkflowStatus } from '../types';

const ACTIVE_STATUSES = new Set(['running', 'started', 'RUNNING', 'PENDING']);
const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled', 'error', 'COMPLETED', 'FAILED']);

export function useMonitorRuns() {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<WorkflowRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load all runs
  const loadRuns = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const data = await getWorkflowRuns();
      setRuns(data);
      if (data.length > 0 && !selectedRun) setSelectedRun(data[0]);
    } catch (e: any) {
      setError(e?.message || 'Failed to load runs');
    } finally {
      setLoading(false);
    }
  }, [selectedRun]);

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

  // FE-MON-1: Cancel a running workflow
  const cancelRun = async (run_id: string) => {
    setActionLoading(true);
    try {
      await apiCancelRun(run_id);
      await loadRuns();
      if (selectedRun?.id === run_id) {
        const updated = await getWorkflowRun(run_id);
        setSelectedRun(updated);
      }
    } catch (e: any) {
      setError(e?.message || 'Failed to cancel run');
    } finally {
      setActionLoading(false);
    }
  };

  // FE-MON-1: Rerun a workflow using its stored config
  const rerunRun = async (config_json: any) => {
    setActionLoading(true);
    try {
      await rerunWorkflow(config_json);
      await loadRuns();
    } catch (e: any) {
      setError(e?.message || 'Failed to rerun workflow');
    } finally {
      setActionLoading(false);
    }
  };

  // FE-MON-4: Auto-refresh polling for active runs
  useEffect(() => {
    const hasActive = runs.some(r => ACTIVE_STATUSES.has(r.status as string));
    const selectedActive = selectedRun && ACTIVE_STATUSES.has(selectedRun.status as string);

    if (hasActive || selectedActive) {
      if (!pollRef.current) {
        pollRef.current = setInterval(async () => {
          // Refresh the run list
          try {
            const data = await getWorkflowRuns();
            setRuns(data);
            // Refresh selected run if it's still active
            if (selectedRun && ACTIVE_STATUSES.has(selectedRun.status as string)) {
              const updated = await getWorkflowRun(selectedRun.id);
              setSelectedRun(updated);
            }
          } catch {
            // ignore polling errors silently
          }
        }, 5000);
      }
    } else {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [runs, selectedRun]);

  return { runs, selectedRun, loading, error, actionLoading, loadRuns, selectRun, cancelRun, rerunRun };
}
