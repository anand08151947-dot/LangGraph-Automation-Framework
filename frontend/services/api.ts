import axios, { AxiosError, AxiosInstance } from 'axios';
import {
  WorkflowConfig,
  SaveTemplateRequest,
  OrchestrationResponse,
  EnglishToJsonResponse,
  CustomizeJsonLLMResponse,
  StatusResponse,
  TemplateInfo,
  Artifact,
} from '../types';

const API_BASE = (import.meta as any).env?.VITE_API_BASE || 'http://localhost:8000';

const api: AxiosInstance = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 15000,
});

// Global error handler
api.interceptors.response.use(
  response => response,
  (error: AxiosError) => {
    if (error.response) {
      console.error('API Error:', error.response.status, error.response.data);
    } else if (error.request) {
      console.error('API No Response:', error.request);
    } else {
      console.error('API Error:', error.message);
    }
    return Promise.reject(error);
  }
);

export const getTemplates = async (): Promise<TemplateInfo[]> => {
  const res = await api.get<TemplateInfo[]>('/templates');
  return res.data;
};

export const getTemplate = async (name: string): Promise<TemplateInfo> => {
  const res = await api.get<TemplateInfo>(`/template/${name}`);
  return res.data;
};

export const saveTemplate = async (data: {
  name: string;
  description?: string;
  template_json: any;
  parent_name?: string;
  sample_prompt?: string;
}): Promise<{ status: string; template: any }> => {
  const res = await api.post('/save_template', data);
  return res.data;
};

export const getCustomTemplates = async (): Promise<any[]> => {
  const res = await api.get('/templates/custom');
  return res.data;
};

export const getTemplateVersions = async (baseName: string): Promise<any[]> => {
  const res = await api.get(`/templates/versions/${encodeURIComponent(baseName)}`);
  return res.data;
};

export const englishToJson = async (instructions: string): Promise<EnglishToJsonResponse> => {
  const res = await api.post<EnglishToJsonResponse>('/english_to_json', { instructions });
  return res.data;
};

export const customizeJsonLLM = async (base_json: any, custom_instructions: string): Promise<CustomizeJsonLLMResponse> => {
  const res = await api.post<CustomizeJsonLLMResponse>('/customize_json_llm', { base_json, custom_instructions });
  return res.data;
};

export const orchestrateAsync = async (config_json: WorkflowConfig): Promise<OrchestrationResponse> => {
  const res = await api.post<OrchestrationResponse>('/orchestrate_async', { config_json });
  return res.data;
};

export const getStatus = async (run_id: string): Promise<StatusResponse> => {
  const res = await api.get<StatusResponse>(`/status/${run_id}`);
  return res.data;
};

export const getConfigSummary = async (): Promise<any> => {
  const res = await api.get('/config/summary');
  return res.data;
};

export const generateConfigLLM = async (instructions: string): Promise<any> => {
  const res = await api.post('/config/generate_llm', { instructions });
  return res.data;
};

export const simulateConfig = async (config_json: any): Promise<any> => {
  const res = await api.post('/config/simulate', { config_json });
  return res.data;
};

export const englishToJsonSubmit = async (instructions: string, llm_response: string) => {
  const res = await api.post('/english_to_json/submit', { instructions, llm_response });
  return res.data;
};

export const customizeJsonLLMSubmit = async (base_json: any, llm_response: string) => {
  const res = await api.post('/customize_json_llm/submit', { base_json, llm_response });
  return res.data;
};

export const downloadBundle = async (params: { artifact_ids: string[] }) => {
  const res = await api.get('/download_bundle', {
    params,
    responseType: 'blob',
  });
  return res.data;
};

// New API functions
export const getConfig = async (): Promise<any> => {
  const res = await api.get('/config');
  return res.data;
};

export const updateLmStudioConfig = async (url: string, model: string): Promise<any> => {
  const res = await api.put('/config/lm_studio', { url, model });
  return res.data;
};

export const getArtifacts = async (): Promise<any[]> => {
  const res = await api.get<any[]>('/artifacts');
  return res.data;
};

export const getArtifactCode = async (run_id: string): Promise<any> => {
  const res = await api.get(`/artifacts/${run_id}/code`);
  return res.data;
};

export const downloadRunBundle = async (run_id: string): Promise<Blob> => {
  const res = await api.get(`/download_bundle/${run_id}`, { responseType: 'blob' });
  return res.data;
};

export const getSystemHealth = async (): Promise<any> => {
  const res = await api.get('/health');
  return res.data;
};

export const getSystemReadiness = async (): Promise<any> => {
  const res = await api.get('/readiness');
  return res.data;
};

export const testLlmConnection = async (params: Record<string, string>): Promise<{ ok: boolean; latency_ms: number; error?: string }> => {
  const res = await api.post('/llm/test', params);
  return res.data;
};

export const updateLlmConfig = async (config: Record<string, string>): Promise<any> => {
  const res = await api.put('/config/llm', config);
  return res.data;
};

export default api;
export const resumeRun = async (run_id: string, config_json: any, approval_input: Record<string, any> = {}): Promise<any> => {
  const res = await api.post(`/resume/${run_id}`, { config_json, approval_input });
  return res.data;
};

export const getApprovalStatus = async (run_id: string): Promise<any> => {
  const res = await api.get(`/approval/${run_id}`);
  return res.data;
};

// FE-BUILD-3: Discover registered tools from the tool registry
export const getRegisteredTools = async (): Promise<any[]> => {
  const res = await api.get<any[]>('/tools');
  return res.data;
};
