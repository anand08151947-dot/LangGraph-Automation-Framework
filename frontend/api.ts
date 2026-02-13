// Download workflow artifact bundle
// params: { artifact_ids: string[] }
export const downloadBundle = async (params: { artifact_ids: string[] }) => {
  // Returns a blob (zip/tarball)
  const res = await api.get('/download_bundle', {
    params,
    responseType: 'blob',
  });
  return res.data;
};
import {
  WorkflowConfig,
  SaveTemplateRequest,
  OrchestrationRequest,
  OrchestrationResponse,
  EnglishToJsonRequest,
  EnglishToJsonResponse,
  CustomizeJsonLLMRequest,
  CustomizeJsonLLMResponse,
  StatusResponse
} from './types';
export const saveTemplate = async (data: SaveTemplateRequest): Promise<{ status: string; filename: string }> => {
  const res = await api.post('/save_template', data);
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
import axios, { AxiosError, AxiosInstance } from 'axios';
import { TemplateInfo } from './types';

const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:8000';

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

export default api;
