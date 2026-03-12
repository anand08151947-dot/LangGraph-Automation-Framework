import { useState } from 'react';
import { downloadBundle, getArtifacts } from '../services/api';
import { Artifact } from '../types';

export function useExportArtifacts() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadArtifacts = async () => {
    setLoading(true); setError(null);
    try {
      const data = await getArtifacts();
      setArtifacts(data);
    } catch (e: any) {
      setError(e?.message || 'Failed to load artifacts');
    } finally {
      setLoading(false);
    }
  };

  // Download selected artifacts as bundle
  const exportBundle = async (artifact_ids: string[]) => {
    setLoading(true); setError(null);
    try {
      const blob = await downloadBundle({ artifact_ids });
      // Trigger browser download
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'workflow_bundle.zip';
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e?.message || 'Export failed');
    } finally {
      setLoading(false);
    }
  };

  return { artifacts, loading, error, loadArtifacts, exportBundle };
}
