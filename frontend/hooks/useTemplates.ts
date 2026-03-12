import { useEffect, useState } from 'react';
import { getTemplates } from '../services/api';
import { TemplateInfo } from '../types';

export function useTemplates() {
  const [data, setData] = useState<TemplateInfo[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getTemplates()
      .then(setData)
      .catch(err => {
        setError(
          err?.response?.data?.detail ||
          err?.message ||
          'Failed to load templates.'
        );
      })
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error };
}
