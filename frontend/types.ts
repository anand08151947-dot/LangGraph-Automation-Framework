// Workflow config structure (simplified, extend as needed)
export interface WorkflowConfig {
  graph_name: string;
  agents: Array<any>; // You can define a more specific Agent type
  mcp_servers?: Record<string, any>;
}

export interface SaveTemplateRequest {
  name: string;
  description?: string;
  example?: Record<string, unknown>;
  version?: string;
}

export interface OrchestrationRequest {
  config_json: WorkflowConfig;
}

export interface OrchestrationResponse {
  run_id: string;
  status: string;
}

export interface EnglishToJsonRequest {
  instructions: string;
}

export interface EnglishToJsonResponse {
  config_json?: WorkflowConfig;
  prompt?: string;
  note?: string;
}

export interface CustomizeJsonLLMRequest {
  base_json: WorkflowConfig;
  custom_instructions: string;
}

export interface CustomizeJsonLLMResponse {
  customized_json?: WorkflowConfig;
  prompt?: string;
  note?: string;
}

export interface StatusResponse {
  run_id: string;
  status: string;
  result?: any;
}

export enum WorkflowStatus {
  RUNNING = 'RUNNING',
  COMPLETED = 'COMPLETED',
  FAILED = 'FAILED',
  PENDING = 'PENDING'
}

export interface Agent {
  id: string;
  name: string;
  role: string;
  tools: string[];
}

export interface WorkflowNode {
  id: string;
  type: 'agent' | 'tool' | 'router';
  label: string;
  position: { x: number; y: number };
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
}

export interface Template {
  id: string;
  name: string;
  description: string;
  domain: string;
  configJson: string;
}

export interface WorkflowRun {
  id: string;
  name: string;
  status: WorkflowStatus;
  startTime: string;
  logs: string[];
  duration?: string;
  memory?: string;
  successRate?: number;
  config?: any;
}

export interface TemplateInfo {
  name: string;
  use_case?: string;
  description?: string;
  sample_prompt?: string;
  example?: Record<string, unknown>;
  source_file?: string;
  version?: string;
}

export interface Artifact {
  id: string;
  name: string;
  type: 'json' | 'code' | 'template' | 'config';
  size: string;
}
