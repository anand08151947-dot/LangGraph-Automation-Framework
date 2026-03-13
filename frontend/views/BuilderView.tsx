import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import ReactDOM from 'react-dom';
import { TemplateInfo } from '../types';
import { useWorkflowBuilder } from '../hooks/useWorkflowBuilder';
import { saveTemplate, orchestrateAsync, getStatus, getCustomTemplates, getTemplateVersions } from '../services/api';

// ── Local Types ──────────────────────────────────────────────────────────────

interface BuilderProps {
  initialTemplate?: { name?: string; description?: string; sample_prompt?: string; example?: any; source_file?: string; } | null;
  onNavigate?: (path: string, data?: any) => void;
}

type NodeType = 'agent' | 'tool_node' | 'conditional' | 'human_node';
type GuardrailAction = 'block' | 'redact' | 'approve';
type OutputFormat = 'text' | 'json' | 'markdown';
type OnFailure = 'retry' | 'error' | 'warn';

interface RoutingRule {
  condition: string;
  next: string;
}

// ── Per-node LLM configuration ────────────────────────────────────────────────
interface LlmConfig {
  temperature?: number;   // 0.0–2.0; default 0.7
  max_tokens?: number;    // default 1024
  model?: string;         // null = use global default
}

// ── Context source for a node ─────────────────────────────────────────────────
type ContextSourceType = 'previous_node' | 'stm' | 'ltm' | 'pre_llm';
interface ContextSource {
  type: ContextSourceType;
  label?: string;         // display label for this source (used in synthesis headers)
  node_id?: string;       // previous_node: inject output of a specific node (blank = last)
  keys?: string[];        // stm: which state keys to inject (blank = all)
  query?: string;         // ltm: keyword filter for LTM entries
  limit?: number;         // ltm: max entries to inject (default 5)
  result_id?: string;     // pre_llm: specific tool call id to inject (blank = all)
}

// ── Synthesis config — how to consolidate multiple context sources ─────────────
type SynthesisStrategy = 'concatenate' | 'structured' | 'summarize';
interface SynthesisConfig {
  strategy?: SynthesisStrategy;
  prompt_template?: string; // custom instruction for 'summarize' strategy
}

// ── Input context guardrail config ────────────────────────────────────────────
type ContextLengthStrategy = 'truncate' | 'summarize' | 'error';
interface InputGuardrailCheck {
  enabled: boolean;
  action?: GuardrailAction;
}
interface InputGuardrailsConfig {
  pii?: InputGuardrailCheck;
  prompt_injection?: InputGuardrailCheck;
  secrets_detection?: InputGuardrailCheck;
  context_length?: { enabled: boolean; max_chars?: number; on_exceed?: ContextLengthStrategy };
  profanity?: InputGuardrailCheck;
  data_classification?: InputGuardrailCheck;
  encoding_sanitization?: { enabled: boolean };
  language_enforcement?: { enabled: boolean; expected_language?: string; action?: GuardrailAction };
}

interface NodeContext {
  sources?: ContextSource[];
  inject_as?: 'system' | 'user';
  synthesis?: SynthesisConfig;
  input_guardrails?: InputGuardrailsConfig;
}

// ── Expected output schema for a node ────────────────────────────────────────
interface ValidationRule {
  field: string;
  operator: '>=' | '<=' | '>' | '<' | '==' | '!=';
  value: string | number;
}
interface OutputSchema {
  format?: OutputFormat;
  state_key?: string;         // write result to this state variable
  required_fields?: string[]; // must be present in JSON output
  validation?: {
    rules?: ValidationRule[];
    on_failure?: OnFailure;
  };
}

// ── Validation config (standalone, merged with output_schema at runtime) ──────
interface NodeValidation {
  enabled?: boolean;
  required_fields?: string[];
  rules?: ValidationRule[];
  on_failure?: OnFailure;
}

// ── Per-check guardrail config ────────────────────────────────────────────────
interface GuardrailCheck {
  enabled: boolean;
  action: GuardrailAction;
  checks?: string[];  // for regulated_advice: ["medical","legal","financial"]
}
interface GuardrailsConfig {
  pii?: GuardrailCheck;
  harmful_content?: GuardrailCheck;
  self_harm?: GuardrailCheck;
  hate_speech?: GuardrailCheck;
  regulated_advice?: GuardrailCheck & { checks?: string[] };
}

// ── Pre-LLM: Tool calls + RAG executed before LLM, results feed into context ─
interface ToolCallConfig {
  id?: string;              // optional label for this call
  tool: string;             // MCP or registered tool name
  input_template: string;   // {state.VAR} placeholders allowed
  output_var?: string;      // write result to state variable
  inject_into_context?: boolean; // default true
}
type RagProvider = 'ltm' | 'chroma' | 'milvus' | 'pinecone' | 'weaviate' | 'local';
interface RagConfig {
  enabled: boolean;
  provider?: RagProvider;
  collection?: string;
  query_template?: string;  // {state.VAR} allowed
  top_k?: number;
  score_threshold?: number;
  output_var?: string;
  inject_into_context?: boolean;
}
interface PreLlmConfig {
  tool_calls?: ToolCallConfig[];
  rag?: RagConfig;
}

interface NodeConfig {
  id: string;
  type: NodeType;
  system_prompt?: string;
  description?: string;
  next?: string;
  checkpoint?: boolean;
  routing_logic?: RoutingRule[];
  tools?: string[];
  memory_access?: string[];
  // ── Per-node advanced fields ─────────────────────────────────────────────
  pre_llm?: PreLlmConfig;
  llm_config?: LlmConfig;
  context?: NodeContext;
  output_schema?: OutputSchema;
  validation?: NodeValidation;
  guardrails?: GuardrailsConfig;
}

interface EdgeConfig {
  from: string;
  to: string;
  condition?: string;
  label?: string;
}

interface McpServer {
  name: string;
  type: 'stdio' | 'http' | 'sse';
  endpoint?: string;
  command?: string;
  args?: string;
  description?: string;
  timeout_ms?: number;
  auth_header?: string;
}

interface StateVar {
  name: string;
  type: 'string' | 'integer' | 'float' | 'boolean' | 'list' | 'dict';
  description?: string;
  default_value?: string;
}

interface ParallelGroup {
  group: string;
  nodes: string;
  timeout_ms?: number;
}

// ── Constants ────────────────────────────────────────────────────────────────

const NODE_BADGES: Record<NodeType, string> = {
  agent: 'bg-indigo-100 text-indigo-700',
  tool_node: 'bg-teal-100 text-teal-700',
  conditional: 'bg-amber-100 text-amber-700',
  human_node: 'bg-rose-100 text-rose-700',
};

const NODE_ICONS: Record<NodeType, string> = {
  agent: 'fa-robot',
  tool_node: 'fa-wrench',
  conditional: 'fa-code-branch',
  human_node: 'fa-user-check',
};

const TABS = [
  { id: 'overview',   label: 'Overview',        icon: 'fa-layer-group' },
  { id: 'schema',     label: 'State Schema',     icon: 'fa-table-columns' },
  { id: 'nodes',      label: 'Nodes',            icon: 'fa-circle-nodes' },
  { id: 'edges',      label: 'Edges',            icon: 'fa-bezier-curve' },
  { id: 'mcp',        label: 'MCP Servers',      icon: 'fa-plug' },
  { id: 'runtime',    label: 'Runtime & Memory', icon: 'fa-microchip' },
  { id: 'advanced',   label: 'Advanced',         icon: 'fa-sliders' },
  { id: 'run',        label: 'Run',              icon: 'fa-play' },
];

// ── Small Helpers ─────────────────────────────────────────────────────────────

// Proper hover tooltip — replaces the broken native title tooltip
const Tooltip: React.FC<{ text: string; children: React.ReactNode }> = ({ text, children }) => (
  <span className="relative group/tip inline-flex">
    {children}
    <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50
      hidden group-hover/tip:flex flex-col items-center">
      <span className="bg-slate-800 text-white text-xs rounded-lg px-3 py-2 shadow-xl max-w-xs text-center leading-relaxed whitespace-normal">
        {text}
      </span>
      <span className="border-4 border-transparent border-t-slate-800 -mt-0.5"></span>
    </span>
  </span>
);

const FieldLabel: React.FC<{ children: React.ReactNode; hint?: string }> = ({ children, hint }) => (
  <label className="flex items-center gap-1.5 text-xs font-bold text-slate-500 uppercase tracking-widest mb-1.5">
    {children}
    {hint && (
      <Tooltip text={hint}>
        <i className="fas fa-circle-info text-slate-300 hover:text-indigo-400 cursor-help transition-colors text-[11px]"></i>
      </Tooltip>
    )}
  </label>
);

// Per-tab collapsible help panel
const HelpPanel: React.FC<{ title: string; items: { icon: string; label: string; desc: string }[] }> = ({ title, items }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="mb-6 border border-indigo-100 bg-indigo-50/60 rounded-xl overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left">
        <span className="flex items-center gap-2 text-xs font-bold text-indigo-700 uppercase tracking-widest">
          <i className="fas fa-circle-question text-indigo-400"></i> {title}
        </span>
        <i className={`fas fa-chevron-${open ? 'up' : 'down'} text-indigo-300 text-xs transition-transform`}></i>
      </button>
      {open && (
        <div className="px-4 pb-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
          {items.map((item, i) => (
            <div key={i} className="flex items-start gap-2.5 p-3 bg-white rounded-lg border border-indigo-100">
              <div className="w-7 h-7 bg-indigo-100 rounded-lg flex items-center justify-center flex-shrink-0">
                <i className={`fas ${item.icon} text-indigo-500 text-xs`}></i>
              </div>
              <div>
                <p className="text-xs font-bold text-slate-700">{item.label}</p>
                <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const Input: React.FC<React.InputHTMLAttributes<HTMLInputElement>> = (props) => (
  <input
    {...props}
    className={`w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all ${props.className ?? ''}`}
  />
);

const Select: React.FC<React.SelectHTMLAttributes<HTMLSelectElement>> = (props) => (
  <select
    {...props}
    className={`w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all ${props.className ?? ''}`}
  />
);

const Textarea: React.FC<React.TextareaHTMLAttributes<HTMLTextAreaElement>> = (props) => (
  <textarea
    {...props}
    className={`w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all resize-none ${props.className ?? ''}`}
  />
);

const SectionTitle: React.FC<{ icon?: string; children: React.ReactNode }> = ({ icon, children }) => (
  <h3 className="text-sm font-bold text-slate-700 flex items-center gap-2 mb-4">
    {icon && <i className={`fas ${icon} text-indigo-400`}></i>}
    {children}
  </h3>
);

const Divider = () => <div className="border-t border-slate-100 my-6" />;

// ── Help content per tab ───────────────────────────────────────────────────────
const HELP: Record<string, { title: string; items: { icon: string; label: string; desc: string }[] }> = {
  overview: {
    title: 'About the Overview tab',
    items: [
      { icon: 'fa-tag', label: 'Graph Name', desc: 'A unique identifier for this workflow. Used as the graph ID at runtime. Use underscores, no spaces. e.g. my_research_pipeline' },
      { icon: 'fa-code-branch', label: 'Version', desc: 'Semantic version of your workflow config. Helps track changes over time. e.g. 1.0, 2.1' },
      { icon: 'fa-align-left', label: 'Description', desc: 'A plain-English description of what this workflow does. Shown in the template library.' },
    ],
  },
  schema: {
    title: 'About State Schema',
    items: [
      { icon: 'fa-database', label: 'What is state?', desc: 'State is a shared context that flows through every node. Each variable is readable and writable by any agent in the graph.' },
      { icon: 'fa-font', label: 'string', desc: 'Text values. e.g. task = "research". Used for task type, status messages, content.' },
      { icon: 'fa-hashtag', label: 'integer', desc: 'Whole numbers. e.g. retry_count = 0. Useful for loops, counters, and retry tracking.' },
      { icon: 'fa-percent', label: 'float', desc: 'Decimal numbers. e.g. confidence_score = 0.85. Used for scores, thresholds, probabilities.' },
      { icon: 'fa-toggle-on', label: 'boolean', desc: 'True/false flags. e.g. approval_required = true. Controls conditional routing decisions.' },
    ],
  },
  nodes: {
    title: 'About Nodes',
    items: [
      { icon: 'fa-robot', label: 'agent', desc: 'An LLM-powered agent with a system prompt. The most common node type. Can use tools, read memory, and route conditionally.' },
      { icon: 'fa-wrench', label: 'tool_node', desc: 'Runs one or more tools without an LLM call. e.g. run tests, call an API, execute code.' },
      { icon: 'fa-code-branch', label: 'conditional', desc: 'A pure routing node — no LLM, no tools. Just evaluates conditions on the state and picks the next node.' },
      { icon: 'fa-user-check', label: 'human_node', desc: 'Pauses the workflow and waits for a human to approve before continuing. Creates a checkpoint for resumption.' },
      { icon: 'fa-route', label: 'Routing Logic', desc: 'Conditions like "task == \'research\'" or "confidence_score < 0.7". Evaluated against current state to pick the next node.' },
      { icon: 'fa-plug', label: 'Tools', desc: 'MCP tool names this node can call. Must match a key defined in the MCP Servers tab.' },
    ],
  },
  edges: {
    title: 'About Edges',
    items: [
      { icon: 'fa-arrow-right', label: 'Simple Edge', desc: 'Unconditional connection from one node to another. Always followed regardless of state.' },
      { icon: 'fa-filter', label: 'Conditional Edge', desc: 'Only followed if the condition evaluates to true. e.g. "missing_data == true" routes back to ResearchAgent.' },
      { icon: 'fa-circle-exclamation', label: 'END', desc: 'Use "END" as the target to terminate the workflow at that node.' },
      { icon: 'fa-info-circle', label: 'vs Routing Logic', desc: 'Edges here are explicit declarations. Routing Logic on a node achieves the same result but is defined per-node. Both are supported.' },
    ],
  },
  mcp: {
    title: 'About MCP Servers',
    items: [
      { icon: 'fa-globe', label: 'http', desc: 'An HTTP/REST MCP server. Provide the base endpoint URL. e.g. https://api.search.example' },
      { icon: 'fa-terminal', label: 'stdio', desc: 'A local MCP server launched as a subprocess. Provide the command and args. e.g. npx @modelcontextprotocol/server-github' },
      { icon: 'fa-satellite-dish', label: 'sse', desc: 'A Server-Sent Events MCP server. Streams tool results over HTTP. Provide the endpoint URL.' },
      { icon: 'fa-key', label: 'Server Name', desc: 'The key used to reference this server from a node\'s tools list. e.g. "web_search" → tools: ["web_search"].' },
    ],
  },
  runtime: {
    title: 'About Runtime & Memory',
    items: [
      { icon: 'fa-repeat', label: 'Max Iterations', desc: 'Hard limit on how many node executions can happen in one run. Prevents infinite loops. Default: 20.' },
      { icon: 'fa-floppy-disk', label: 'Checkpoint Store', desc: 'Where to persist state checkpoints. SQLite is local/simple. Postgres is for production scale.' },
      { icon: 'fa-eye', label: 'Tracing', desc: 'Enable step-by-step tracing. LangSmith provides a visual trace UI. "logging" writes to server logs.' },
      { icon: 'fa-brain', label: 'Short-Term Memory', desc: 'In-graph state (graph_state) is the default — shared dict between nodes. Redis for high-throughput.' },
      { icon: 'fa-server', label: 'Long-Term Memory', desc: 'Persists across runs. SQLite for local. Vector DB (Milvus/Pinecone) for semantic search across history.' },
    ],
  },
  advanced: {
    title: 'About Advanced Options',
    items: [
      { icon: 'fa-layer-group', label: 'Parallel Groups', desc: 'Run multiple nodes simultaneously. e.g. ResearchAgent and DataAgent can run in parallel. Results are merged before the next node.' },
      { icon: 'fa-arrows-rotate', label: 'Retry Policy', desc: 'Auto-retry failed nodes up to max_retries times. increment_state names the state variable to increment on each retry.' },
      { icon: 'fa-bookmark', label: 'Checkpointing', desc: 'Save state at specific nodes. Allows the workflow to resume from that point if interrupted, or after a human_node approval.' },
      { icon: 'fa-chart-line', label: 'Observability Hooks', desc: 'Fine-grained control over what gets logged: node traces, state transitions, and agent outputs.' },
    ],
  },
  run: {
    title: 'About Running Workflows',
    items: [
      { icon: 'fa-save', label: 'Save as Template', desc: 'Persists this workflow config to the template library so it can be reused or shared.' },
      { icon: 'fa-play', label: 'Run Workflow', desc: 'Submits the config to the backend orchestrator. The graph is compiled and executed step-by-step.' },
      { icon: 'fa-list-check', label: 'Execution Logs', desc: 'Live step-by-step output as the workflow runs. Shows which node is executing and any errors.' },
      { icon: 'fa-circle-check', label: 'Result', desc: 'The final state output after all nodes complete. Contains all state variables with their final values.' },
    ],
  },
};

// ── Condition Builder ──────────────────────────────────────────────────────────
// Generates condition strings from state variables with smart operator suggestions.

interface StateVarMeta { name: string; type: 'string' | 'integer' | 'float' | 'boolean' | 'list' | 'dict'; }

const OPS_BY_TYPE: Record<string, { op: string; label: string; valuePlaceholder: string; values?: string[] }[]> = {
  string:  [
    { op: "==", label: "equals", valuePlaceholder: "'value'" },
    { op: "!=", label: "not equals", valuePlaceholder: "'value'" },
  ],
  integer: [
    { op: "==", label: "equals", valuePlaceholder: "0" },
    { op: ">",  label: "greater than", valuePlaceholder: "0" },
    { op: ">=", label: ">=", valuePlaceholder: "0" },
    { op: "<",  label: "less than", valuePlaceholder: "0" },
    { op: "<=", label: "<=", valuePlaceholder: "0" },
  ],
  float: [
    { op: ">=", label: ">=", valuePlaceholder: "0.7" },
    { op: ">",  label: ">", valuePlaceholder: "0.7" },
    { op: "<",  label: "<", valuePlaceholder: "0.7" },
    { op: "<=", label: "<=", valuePlaceholder: "0.7" },
    { op: "==", label: "==", valuePlaceholder: "1.0" },
  ],
  boolean: [
    { op: "== true",  label: "is true",  valuePlaceholder: "", values: ["true"] },
    { op: "== false", label: "is false", valuePlaceholder: "", values: ["false"] },
  ],
};

const CONDITION_EXAMPLES = [
  { label: "task == 'research'",       desc: "String equality" },
  { label: "task == 'code'",           desc: "String equality" },
  { label: "confidence_score >= 0.7",  desc: "Float threshold (pass)" },
  { label: "confidence_score < 0.7",   desc: "Float threshold (fail)" },
  { label: "retry_count > 3",          desc: "Integer counter" },
  { label: "missing_data == true",     desc: "Boolean flag" },
  { label: "approval_required == true",desc: "Boolean flag" },
  { label: "resolved == false",        desc: "Boolean flag" },
];

const ConditionBuilder: React.FC<{
  value: string;
  onChange: (v: string) => void;
  stateVars: StateVarMeta[];
  placeholder?: string;
}> = ({ value, onChange, stateVars, placeholder }) => {
  const [showBuilder, setShowBuilder] = useState(false);
  const [selVar, setSelVar] = useState('');
  const [selOp, setSelOp] = useState('');
  const [selVal, setSelVal] = useState('');
  const [showExamples, setShowExamples] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const selectedVarMeta = stateVars.find(v => v.name === selVar);
  const ops = selectedVarMeta ? OPS_BY_TYPE[selectedVarMeta.type] ?? [] : [];

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setShowBuilder(false);
        setShowExamples(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const applyBuilt = () => {
    if (!selVar || !selOp) return;
    const isBoolean = selectedVarMeta?.type === 'boolean';
    const cond = isBoolean ? `${selVar} ${selOp}` : `${selVar} ${selOp} ${selVal}`;
    onChange(cond.trim());
    setShowBuilder(false);
    setSelVar(''); setSelOp(''); setSelVal('');
  };

  const handleVarChange = (varName: string) => {
    setSelVar(varName);
    setSelOp('');
    setSelVal('');
    // Pre-select first op for the type
    const meta = stateVars.find(v => v.name === varName);
    if (meta) {
      const firstOp = OPS_BY_TYPE[meta.type]?.[0];
      if (firstOp) setSelOp(firstOp.op);
    }
  };

  return (
    <div className="flex gap-1.5 items-center flex-1 relative" ref={ref}>
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder ?? "condition (optional)"}
        className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all font-mono"
      />
      {/* Builder toggle */}
      {stateVars.length > 0 && (
        <Tooltip text="Build condition from state variables">
          <button
            onClick={() => { setShowBuilder(b => !b); setShowExamples(false); }}
            className={`flex-shrink-0 w-8 h-8 rounded-lg border flex items-center justify-center transition-colors ${showBuilder ? 'bg-indigo-600 border-indigo-600 text-white' : 'bg-white border-slate-200 text-slate-400 hover:border-indigo-400 hover:text-indigo-600'}`}>
            <i className="fas fa-wand-magic-sparkles text-xs"></i>
          </button>
        </Tooltip>
      )}
      {/* Examples toggle */}
      <Tooltip text="Show condition examples">
        <button
          onClick={() => { setShowExamples(b => !b); setShowBuilder(false); }}
          className={`flex-shrink-0 w-8 h-8 rounded-lg border flex items-center justify-center transition-colors ${showExamples ? 'bg-amber-500 border-amber-500 text-white' : 'bg-white border-slate-200 text-slate-400 hover:border-amber-400 hover:text-amber-600'}`}>
          <i className="fas fa-lightbulb text-xs"></i>
        </button>
      </Tooltip>

      {/* Builder dropdown */}
      {showBuilder && (
        <div className="absolute top-full left-0 mt-1 z-50 bg-white border border-indigo-200 rounded-xl shadow-xl p-4 min-w-[340px]">
          <p className="text-xs font-bold text-indigo-700 uppercase tracking-widest mb-3 flex items-center gap-2">
            <i className="fas fa-wand-magic-sparkles text-indigo-400"></i> Condition Builder
          </p>
          <div className="space-y-2">
            <div>
              <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">State Variable</label>
              <select value={selVar} onChange={e => handleVarChange(e.target.value)}
                className="w-full mt-1 px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none">
                <option value="">— pick variable —</option>
                {stateVars.map(v => (
                  <option key={v.name} value={v.name}>{v.name} ({v.type})</option>
                ))}
              </select>
            </div>
            {selVar && (
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Operator</label>
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {ops.map(o => (
                    <button key={o.op} onClick={() => setSelOp(o.op)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-bold border transition-colors ${selOp === o.op ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-slate-50 text-slate-600 border-slate-200 hover:border-indigo-400'}`}>
                      {o.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {selVar && selOp && selectedVarMeta?.type !== 'boolean' && (
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Value</label>
                <input value={selVal} onChange={e => setSelVal(e.target.value)}
                  placeholder={ops.find(o => o.op === selOp)?.valuePlaceholder ?? 'value'}
                  className="w-full mt-1 px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm font-mono focus:outline-none focus:border-indigo-400" />
              </div>
            )}
            {selVar && selOp && (
              <div className="pt-1">
                <div className="text-[10px] text-slate-400 mb-2 font-mono bg-slate-50 rounded-lg px-3 py-2 border border-slate-200">
                  Preview: <span className="text-indigo-600 font-bold">
                    {selectedVarMeta?.type === 'boolean' ? `${selVar} ${selOp}` : `${selVar} ${selOp} ${selVal || '…'}`}
                  </span>
                </div>
                <button onClick={applyBuilt}
                  className="w-full py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-lg text-xs transition-colors">
                  Apply Condition
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Examples dropdown */}
      {showExamples && (
        <div className="absolute top-full left-0 mt-1 z-50 bg-white border border-amber-200 rounded-xl shadow-xl p-3 min-w-[320px]">
          <p className="text-xs font-bold text-amber-700 uppercase tracking-widest mb-2 flex items-center gap-2">
            <i className="fas fa-lightbulb text-amber-400"></i> Common Conditions
          </p>
          <p className="text-[10px] text-slate-500 mb-3">Click to use. Supported operators: ==, !=, &lt;, &gt;, &lt;=, &gt;=, == true, == false</p>
          <div className="space-y-1">
            {[...CONDITION_EXAMPLES, ...stateVars.flatMap(v => {
              if (v.type === 'boolean') return [
                { label: `${v.name} == true`, desc: `When ${v.name} is set` },
                { label: `${v.name} == false`, desc: `When ${v.name} is not set` },
              ];
              if (v.type === 'float') return [{ label: `${v.name} >= 0.7`, desc: 'Float threshold' }];
              if (v.type === 'integer') return [{ label: `${v.name} > 3`, desc: 'Integer limit' }];
              return [];
            })].map((ex, idx) => (
              <button key={idx} onClick={() => { onChange(ex.label); setShowExamples(false); }}
                className="w-full flex items-center justify-between px-3 py-2 rounded-lg hover:bg-amber-50 transition-colors group text-left">
                <span className="font-mono text-xs text-slate-800 group-hover:text-amber-700">{ex.label}</span>
                <span className="text-[10px] text-slate-400 ml-2 flex-shrink-0">{ex.desc}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

// ── Save As Modal ──────────────────────────────────────────────────────────────

const SaveAsModal: React.FC<{
  open: boolean;
  initialName: string;
  initialDescription: string;
  parentName?: string;
  versions: any[];
  onClose: () => void;
  onSave: (name: string, description: string) => void;
  saving: boolean;
}> = ({ open, initialName, initialDescription, parentName, versions, onClose, onSave, saving }) => {
  const [name, setName] = useState(initialName);
  const [desc, setDesc] = useState(initialDescription);

  useEffect(() => { setName(initialName); setDesc(initialDescription); }, [initialName, initialDescription, open]);

  if (!open) return null;

  const latestVersion = versions.reduce((max, v) => Math.max(max, v.version ?? 1), 0);
  const nextVersion = latestVersion + 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-base font-bold text-slate-800 flex items-center gap-2">
              <i className="fas fa-save text-indigo-500"></i> Save Template
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">Persist this workflow for future use and further customization</p>
          </div>
          <button onClick={onClose} className="text-slate-300 hover:text-slate-600 transition-colors">
            <i className="fas fa-xmark text-lg"></i>
          </button>
        </div>
        <div className="p-6 space-y-4">
          {parentName && (
            <div className="flex items-center gap-2 p-3 bg-indigo-50 border border-indigo-100 rounded-xl text-xs text-indigo-700">
              <i className="fas fa-code-branch"></i>
              <span>Derived from: <strong>{parentName}</strong></span>
            </div>
          )}
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-1.5">Template Name / Identifier</label>
            <input value={name} onChange={e => setName(e.target.value)}
              className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" />
            <p className="text-[10px] text-slate-400 mt-1">Use underscores, no spaces. A new name creates a new entry; the same name increments the version.</p>
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-1.5">Description</label>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={3}
              className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all resize-none" />
          </div>
          {versions.length > 0 && (
            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Existing Versions</label>
              <div className="space-y-1.5 max-h-32 overflow-auto">
                {versions.map((v, i) => (
                  <div key={i} className="flex items-center justify-between px-3 py-2 bg-slate-50 rounded-lg border border-slate-200 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-slate-700">{v.name}</span>
                      {v.is_custom && <span className="px-1.5 py-0.5 bg-indigo-100 text-indigo-600 rounded text-[10px] font-bold">custom</span>}
                    </div>
                    <div className="flex items-center gap-2 text-slate-400">
                      <span className="font-bold text-indigo-600">v{v.version ?? 1}</span>
                      {v.updated_at && <span>{new Date(v.updated_at).toLocaleDateString()}</span>}
                    </div>
                  </div>
                ))}
              </div>
              {name === initialName && (
                <p className="text-[10px] text-amber-600 mt-1.5 flex items-center gap-1">
                  <i className="fas fa-circle-info"></i>
                  Saving with same name will create <strong>v{nextVersion}</strong>
                </p>
              )}
            </div>
          )}
        </div>
        <div className="flex gap-3 px-6 py-4 border-t border-slate-100">
          <button onClick={onClose} className="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold rounded-xl text-sm transition-colors">
            Cancel
          </button>
          <button onClick={() => onSave(name, desc)} disabled={!name.trim() || saving}
            className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold rounded-xl text-sm flex items-center justify-center gap-2 transition-colors">
            {saving ? <><i className="fas fa-spinner fa-spin"></i> Saving…</> : <><i className="fas fa-save"></i> Save Template</>}
          </button>
        </div>
      </div>
    </div>
  );
};

// ── NodeSubSection — collapsible sub-panel for NodeDetailPanel ────────────────

const NodeSubSection: React.FC<{
  icon: string;
  title: string;
  hint?: string;
  children: React.ReactNode;
}> = ({ icon, title, hint, children }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2.5 px-3 py-2.5 bg-slate-50 hover:bg-slate-100 transition-colors text-left">
        <i className={`fas ${icon} text-indigo-400 text-xs w-4 text-center flex-shrink-0`}></i>
        <span className="text-xs font-bold text-slate-600 flex-1">{title}</span>
        {hint && (
          <Tooltip text={hint}>
            <span className="text-slate-300 hover:text-indigo-400 text-xs mr-1">
              <i className="fas fa-circle-info"></i>
            </span>
          </Tooltip>
        )}
        <i className={`fas fa-chevron-${open ? 'up' : 'down'} text-slate-300 text-[10px]`}></i>
      </button>
      {open && (
        <div className="p-3 space-y-3 bg-white">
          {children}
        </div>
      )}
    </div>
  );
};

// ── Node Detail Panel ─────────────────────────────────────────────────────────

const NodeDetailPanel: React.FC<{
  node: NodeConfig;
  onChange: (n: NodeConfig) => void;
  stateKeys: string[];
  stateVars: StateVarMeta[];
}> = ({ node, onChange, stateKeys, stateVars }) => {
  const [toolInput, setToolInput] = useState('');

  const addTool = () => {
    if (!toolInput.trim()) return;
    onChange({ ...node, tools: [...(node.tools ?? []), toolInput.trim()] });
    setToolInput('');
  };

  const addRoute = () => {
    onChange({ ...node, routing_logic: [...(node.routing_logic ?? []), { condition: '', next: '' }] });
  };

  const updateRoute = (i: number, r: RoutingRule) => {
    const rl = [...(node.routing_logic ?? [])];
    rl[i] = r;
    onChange({ ...node, routing_logic: rl });
  };

  const removeRoute = (i: number) => {
    onChange({ ...node, routing_logic: (node.routing_logic ?? []).filter((_, idx) => idx !== i) });
  };

  const toggleMemory = (val: string) => {
    const ma = node.memory_access ?? [];
    onChange({ ...node, memory_access: ma.includes(val) ? ma.filter(v => v !== val) : [...ma, val] });
  };

  return (
    <div className="space-y-5">
      {/* ID + Type */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <FieldLabel hint="Unique identifier used to reference this node">Node ID</FieldLabel>
          <Input value={node.id} onChange={e => onChange({ ...node, id: e.target.value })} placeholder="e.g. Planner" />
        </div>
        <div>
          <FieldLabel hint="Determines the node behavior in the graph">Node Type</FieldLabel>
          <Select value={node.type} onChange={e => onChange({ ...node, type: e.target.value as NodeType })}>
            <option value="agent">agent — LLM agent</option>
            <option value="tool_node">tool_node — runs tools</option>
            <option value="conditional">conditional — routing only</option>
            <option value="human_node">human_node — pauses for human</option>
          </Select>
        </div>
      </div>

      {/* System prompt (agent only) */}
      {node.type === 'agent' && (
        <div>
          <FieldLabel hint="The system prompt sent to the LLM for this agent">System Prompt</FieldLabel>
          <Textarea
            rows={4}
            value={node.system_prompt ?? ''}
            onChange={e => onChange({ ...node, system_prompt: e.target.value })}
            placeholder="You are a research agent. Your job is to..."
          />
        </div>
      )}

      {/* Description (tool_node / human_node) */}
      {(node.type === 'tool_node' || node.type === 'human_node') && (
        <div>
          <FieldLabel hint="Human-readable description of what this node does">Description</FieldLabel>
          <Input value={node.description ?? ''} onChange={e => onChange({ ...node, description: e.target.value })} placeholder="e.g. Run test suite" />
        </div>
      )}

      {/* Checkpoint (human_node) */}
      {node.type === 'human_node' && (
        <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
          <input type="checkbox" checked={!!node.checkpoint} onChange={e => onChange({ ...node, checkpoint: e.target.checked })} className="w-4 h-4 rounded" />
          <span>Create checkpoint at this node</span>
          <span className="text-slate-400 text-xs">(saves state for resumption)</span>
        </label>
      )}

      {/* Simple next (non-conditional) */}
      {node.type !== 'conditional' && (
        <div>
          <FieldLabel hint="Default next node when routing_logic is not used">Next Node (default)</FieldLabel>
          <Input value={node.next ?? ''} onChange={e => onChange({ ...node, next: e.target.value })} placeholder="e.g. Supervisor or END" />
        </div>
      )}

      {/* Routing logic */}
      {(node.type === 'conditional' || node.type === 'agent') && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <FieldLabel hint="Conditional rules that determine which node to go to next. Each rule is evaluated in order; the first matching condition determines the next node.">Routing Logic</FieldLabel>
            <button onClick={addRoute} className="text-xs px-2 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 rounded-lg transition-colors">
              + Add Rule
            </button>
          </div>
          <div className="space-y-2">
            {(node.routing_logic ?? []).map((r, i) => (
              <div key={i} className="flex gap-2 items-center">
                <ConditionBuilder
                  value={r.condition}
                  onChange={v => updateRoute(i, { ...r, condition: v })}
                  stateVars={stateVars}
                  placeholder="condition (e.g. task == 'research')"
                />
                <span className="text-slate-400 text-sm flex-shrink-0">→</span>
                <Input value={r.next} onChange={e => updateRoute(i, { ...r, next: e.target.value })} placeholder="next node id" className="w-36 flex-shrink-0" />
                <button onClick={() => removeRoute(i)} className="text-slate-300 hover:text-rose-500 transition-colors flex-shrink-0">
                  <i className="fas fa-xmark"></i>
                </button>
              </div>
            ))}
            {(node.routing_logic ?? []).length === 0 && (
              <p className="text-xs text-slate-400 italic">No routing rules yet. Add a rule above.</p>
            )}
          </div>
        </div>
      )}

      {/* Tools */}
      {(node.type === 'agent' || node.type === 'tool_node') && (
        <div>
          <FieldLabel hint="MCP tool names this node is allowed to use">Tools</FieldLabel>
          <div className="flex gap-2 mb-2">
            <Input value={toolInput} onChange={e => setToolInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') addTool(); }}
              placeholder="tool name (press Enter)" className="flex-1" />
            <button onClick={addTool} className="px-3 py-2 bg-indigo-600 text-white rounded-lg text-xs font-bold hover:bg-indigo-700 transition-colors">+</button>
          </div>
          <div className="flex flex-wrap gap-1">
            {(node.tools ?? []).map((t, ti) => (
              <span key={ti} className="flex items-center gap-1 px-2 py-1 bg-indigo-50 text-indigo-700 rounded-full text-xs font-medium">
                {t}
                <button onClick={() => onChange({ ...node, tools: (node.tools ?? []).filter((_, i) => i !== ti) })} className="hover:text-indigo-900">×</button>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Memory access */}
      <div>
        <FieldLabel hint="Which memory stores this node can read/write">Memory Access</FieldLabel>
        <div className="flex gap-4">
          {['short_term', 'long_term'].map(m => (
            <label key={m} className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
              <input type="checkbox" checked={(node.memory_access ?? []).includes(m)} onChange={() => toggleMemory(m)} className="w-4 h-4 rounded" />
              {m.replace('_', ' ')}
            </label>
          ))}
        </div>
      </div>

      {/* ── LLM Config (agent only) ─────────────────────────────────────────── */}
      {node.type === 'agent' && (
        <NodeSubSection icon="fa-sliders" title="LLM Config"
          hint="Per-node LLM parameters. Leave blank to use the global default from Settings.">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <FieldLabel hint="Controls randomness: 0=deterministic, 1=balanced, 2=creative">Temperature</FieldLabel>
              <div className="flex items-center gap-3">
                <input type="range" min="0" max="2" step="0.05"
                  value={node.llm_config?.temperature ?? 0.7}
                  onChange={e => onChange({ ...node, llm_config: { ...node.llm_config, temperature: parseFloat(e.target.value) } })}
                  className="flex-1 h-1.5 accent-indigo-600" />
                <span className="text-xs font-mono text-slate-600 w-8 text-right">
                  {(node.llm_config?.temperature ?? 0.7).toFixed(2)}
                </span>
              </div>
            </div>
            <div>
              <FieldLabel hint="Maximum tokens the LLM can output for this node">Max Tokens</FieldLabel>
              <Input type="number" min={64} max={16384}
                value={node.llm_config?.max_tokens ?? ''}
                onChange={e => onChange({ ...node, llm_config: { ...node.llm_config, max_tokens: parseInt(e.target.value) || undefined } })}
                placeholder="1024 (default)" />
            </div>
          </div>
          <div>
            <FieldLabel hint="Override the model for this node only (e.g. gpt-4o, mistral-7b). Leave blank for global default.">Model Override</FieldLabel>
            <Input value={node.llm_config?.model ?? ''}
              onChange={e => onChange({ ...node, llm_config: { ...node.llm_config, model: e.target.value || undefined } })}
              placeholder="e.g. gpt-4o or mistral-7b (blank = use default)" />
          </div>
        </NodeSubSection>
      )}

      {/* ── Pre-LLM: Tool Calls ──────────────────────────────────────────────── */}
      {node.type === 'agent' && (
        <NodeSubSection icon="fa-bolt" title="Pre-LLM: Tool Calls"
          hint="Execute MCP or registered tools BEFORE the LLM call. Results are injected as grounding material into the prompt. Use {state.VAR} to reference workflow state variables in the input template.">
          <div className="space-y-3">
            {(node.pre_llm?.tool_calls ?? []).map((tc, ti) => (
              <div key={ti} className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold text-indigo-600 uppercase tracking-widest">Tool Call #{ti + 1}</span>
                  <button onClick={() => {
                    const calls = [...(node.pre_llm?.tool_calls ?? [])];
                    calls.splice(ti, 1);
                    onChange({ ...node, pre_llm: { ...node.pre_llm, tool_calls: calls } });
                  }} className="text-red-400 hover:text-red-600 text-xs"><i className="fas fa-trash-can"></i></button>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <FieldLabel hint="Optional display name for this tool call">Label (id)</FieldLabel>
                    <input value={tc.id ?? ''} placeholder="e.g. search_call"
                      onChange={e => {
                        const calls = [...(node.pre_llm?.tool_calls ?? [])];
                        calls[ti] = { ...tc, id: e.target.value || undefined };
                        onChange({ ...node, pre_llm: { ...node.pre_llm, tool_calls: calls } });
                      }}
                      className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs font-mono" />
                  </div>
                  <div>
                    <FieldLabel hint="MCP tool name or registered tool. Must match a key in mcp_servers or tool_registry.">Tool Name *</FieldLabel>
                    <input value={tc.tool} placeholder="e.g. web_search"
                      onChange={e => {
                        const calls = [...(node.pre_llm?.tool_calls ?? [])];
                        calls[ti] = { ...tc, tool: e.target.value };
                        onChange({ ...node, pre_llm: { ...node.pre_llm, tool_calls: calls } });
                      }}
                      className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs font-mono" />
                  </div>
                </div>
                <div>
                  <FieldLabel hint="What to send to the tool. Use {state.VARNAME} to inject state variables. Example: 'Search for: {state.task}'">Input Template *</FieldLabel>
                  <input value={tc.input_template} placeholder="e.g. {state.task}"
                    onChange={e => {
                      const calls = [...(node.pre_llm?.tool_calls ?? [])];
                      calls[ti] = { ...tc, input_template: e.target.value };
                      onChange({ ...node, pre_llm: { ...node.pre_llm, tool_calls: calls } });
                    }}
                    className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs font-mono" />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <FieldLabel hint="Optional: write tool result to this state variable so other nodes can access it.">Output → State Var</FieldLabel>
                    <input value={tc.output_var ?? ''} placeholder="e.g. search_results"
                      onChange={e => {
                        const calls = [...(node.pre_llm?.tool_calls ?? [])];
                        calls[ti] = { ...tc, output_var: e.target.value || undefined };
                        onChange({ ...node, pre_llm: { ...node.pre_llm, tool_calls: calls } });
                      }}
                      className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs font-mono" />
                  </div>
                  <div className="flex items-end pb-1">
                    <label className="flex items-center gap-2 cursor-pointer text-xs">
                      <input type="checkbox" checked={tc.inject_into_context !== false}
                        onChange={e => {
                          const calls = [...(node.pre_llm?.tool_calls ?? [])];
                          calls[ti] = { ...tc, inject_into_context: e.target.checked };
                          onChange({ ...node, pre_llm: { ...node.pre_llm, tool_calls: calls } });
                        }} className="w-3.5 h-3.5 rounded" />
                      <span className="text-slate-600">Inject into LLM context</span>
                    </label>
                  </div>
                </div>
              </div>
            ))}
            <button onClick={() => {
              const calls = [...(node.pre_llm?.tool_calls ?? [])];
              calls.push({ tool: '', input_template: '{state.task}', inject_into_context: true });
              onChange({ ...node, pre_llm: { ...node.pre_llm, tool_calls: calls } });
            }} className="text-xs px-2.5 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 rounded-lg transition-colors">
              + Add Tool Call
            </button>
          </div>
        </NodeSubSection>
      )}

      {/* ── Pre-LLM: RAG / Semantic Search ───────────────────────────────────── */}
      {node.type === 'agent' && (
        <NodeSubSection icon="fa-magnifying-glass-chart" title="Pre-LLM: RAG / Semantic Search"
          hint="Run a semantic similarity search BEFORE the LLM call. Retrieved document chunks are injected as grounding context. Supports LTM (built-in), Chroma, Milvus, Pinecone, and Weaviate.">
          {(() => {
            const rag = node.pre_llm?.rag ?? {} as RagConfig;
            const setRag = (patch: Partial<RagConfig>) =>
              onChange({ ...node, pre_llm: { ...node.pre_llm, rag: { ...rag, ...patch } } });
            return (
              <div className="space-y-3">
                <label className="flex items-center gap-2 cursor-pointer text-xs">
                  <input type="checkbox" checked={!!rag.enabled}
                    onChange={e => setRag({ enabled: e.target.checked })}
                    className="w-3.5 h-3.5 rounded" />
                  <span className={`font-bold ${rag.enabled ? 'text-indigo-600' : 'text-slate-500'}`}>Enable RAG search for this node</span>
                </label>
                {rag.enabled && (
                  <div className="space-y-2.5 pl-1">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <FieldLabel hint="Vector store backend. 'ltm' uses the built-in LTM memory. Others require external SDK wiring in the backend.">Provider</FieldLabel>
                        <Select value={rag.provider ?? 'ltm'} onChange={e => setRag({ provider: e.target.value as RagProvider })}>
                          <option value="ltm">LTM (built-in)</option>
                          <option value="chroma">ChromaDB</option>
                          <option value="milvus">Milvus</option>
                          <option value="pinecone">Pinecone</option>
                          <option value="weaviate">Weaviate</option>
                          <option value="local">Local (file)</option>
                        </Select>
                      </div>
                      <div>
                        <FieldLabel hint="Collection or index name in the vector store.">Collection / Index</FieldLabel>
                        <input value={rag.collection ?? ''} placeholder="e.g. enterprise_memory"
                          onChange={e => setRag({ collection: e.target.value })}
                          className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs font-mono" />
                      </div>
                    </div>
                    <div>
                      <FieldLabel hint="Search query template. Use {state.VAR} to inject state variables. Example: '{state.task} context'">Query Template *</FieldLabel>
                      <input value={rag.query_template ?? ''} placeholder="e.g. {state.task}"
                        onChange={e => setRag({ query_template: e.target.value })}
                        className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs font-mono" />
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                      <div>
                        <FieldLabel hint="Number of top matching chunks to retrieve (default 5).">Top-K</FieldLabel>
                        <input type="number" min={1} max={50} value={rag.top_k ?? 5}
                          onChange={e => setRag({ top_k: parseInt(e.target.value) || 5 })}
                          className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs font-mono" />
                      </div>
                      <div>
                        <FieldLabel hint="Minimum similarity score to include a chunk (0.0 = no filter, 1.0 = exact match).">Min Score</FieldLabel>
                        <input type="number" min={0} max={1} step={0.05} value={rag.score_threshold ?? 0}
                          onChange={e => setRag({ score_threshold: parseFloat(e.target.value) || 0 })}
                          className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs font-mono" />
                      </div>
                      <div>
                        <FieldLabel hint="Optional: write retrieved chunks to this state variable.">Output → State Var</FieldLabel>
                        <input value={rag.output_var ?? ''} placeholder="e.g. rag_results"
                          onChange={e => setRag({ output_var: e.target.value || undefined })}
                          className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs font-mono" />
                      </div>
                    </div>
                    <label className="flex items-center gap-2 cursor-pointer text-xs">
                      <input type="checkbox" checked={rag.inject_into_context !== false}
                        onChange={e => setRag({ inject_into_context: e.target.checked })}
                        className="w-3.5 h-3.5 rounded" />
                      <span className="text-slate-600">Inject retrieved chunks into LLM context</span>
                    </label>
                  </div>
                )}
              </div>
            );
          })()}
        </NodeSubSection>
      )}

      {/* ── Context Sources (agent only) ────────────────────────────────────── */}
      {node.type === 'agent' && (
        <NodeSubSection icon="fa-layer-group" title="Context Sources"
          hint={[
            "Defines what context is assembled and injected before the LLM call. Sources are collected in order and combined according to the synthesis strategy.",
            "",
            "Source types:",
            "• previous_node — inject the output of a specific prior node (leave node ID blank for the most recent message). Use this to chain agent outputs.",
            "• stm — inject Short-Term Memory keys from the current workflow state. Good for passing task metadata, scores, or flags between nodes.",
            "• ltm — inject Long-Term Memory entries (SQLite history). Use a keyword filter to retrieve relevant past sessions.",
            "• pre_llm — inject results from Tool Calls or RAG searches that ran in the Pre-LLM steps above. Use result_id to pick a specific call, or leave blank for all results.",
            "",
            "Label: Give each source a display name (shown in synthesis headers and artifact logs).",
            "",
            "Synthesis (multi-source): When you have 2+ sources:",
            "• concatenate — each chunk is injected as a separate labelled block (default, safe for most cases).",
            "• structured — all chunks merged into one numbered message under '--- Consolidated Context ---'.",
            "• summarize — all chunks prefixed with a synthesis instruction so the LLM consolidates them before answering. You can customize the instruction.",
            "",
            "Inject as: controls whether context appears as a 'user' turn or a 'system' turn in the LLM conversation.",
          ].join("\n")}>
          <div className="space-y-2">
            {(node.context?.sources ?? []).map((src, si) => {
              const updateSrc = (patch: Partial<ContextSource>) => {
                const sources = [...(node.context?.sources ?? [])];
                sources[si] = { ...src, ...patch };
                onChange({ ...node, context: { ...node.context, sources } });
              };
              return (
                <div key={si} className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg space-y-2">
                  {/* Row 1: type + label + delete */}
                  <div className="flex gap-2 items-center">
                    <Select value={src.type}
                      onChange={e => updateSrc({ type: e.target.value as ContextSourceType, node_id: undefined, keys: undefined, query: undefined, result_id: undefined })}
                      className="w-36 flex-shrink-0 text-xs">
                      <option value="previous_node">previous_node</option>
                      <option value="stm">stm (short-term)</option>
                      <option value="ltm">ltm (long-term)</option>
                      <option value="pre_llm">pre_llm (tool/RAG)</option>
                    </Select>
                    <Input value={src.label ?? ''} placeholder="label (optional)"
                      className="flex-1 text-xs"
                      onChange={e => updateSrc({ label: e.target.value || undefined })} />
                    <button onClick={() => {
                      const sources = (node.context?.sources ?? []).filter((_, i) => i !== si);
                      onChange({ ...node, context: { ...node.context, sources } });
                    }} className="text-slate-300 hover:text-rose-500 transition-colors flex-shrink-0">
                      <i className="fas fa-xmark text-xs"></i>
                    </button>
                  </div>
                  {/* Row 2: type-specific config */}
                  {src.type === 'previous_node' && (
                    <div className="ml-1">
                      <FieldLabel hint="The node ID whose output you want to inject. Leave blank to use the most recent message from any node.">Node ID (blank = last output)</FieldLabel>
                      <Input value={src.node_id ?? ''} placeholder="e.g. ResearchAgent"
                        className="text-xs w-full"
                        onChange={e => updateSrc({ node_id: e.target.value || undefined })} />
                    </div>
                  )}
                  {src.type === 'stm' && (
                    <div className="ml-1">
                      <FieldLabel hint="Comma-separated list of state variable names to inject. Leave blank to inject all STM keys. Example: task, confidence_score, retry_count">State Keys (blank = all)</FieldLabel>
                      <Input value={(src.keys ?? []).join(', ')} placeholder="e.g. task, confidence_score"
                        className="text-xs w-full"
                        onChange={e => updateSrc({ keys: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })} />
                    </div>
                  )}
                  {src.type === 'ltm' && (
                    <div className="ml-1 grid grid-cols-2 gap-2">
                      <div>
                        <FieldLabel hint="Keyword to filter LTM entries. Only entries containing this word will be injected. Leave blank to inject the most recent entries.">Keyword Filter (optional)</FieldLabel>
                        <Input value={src.query ?? ''} placeholder="e.g. customer, research"
                          className="text-xs"
                          onChange={e => updateSrc({ query: e.target.value || undefined })} />
                      </div>
                      <div>
                        <FieldLabel hint="Maximum number of LTM entries to inject (default 5). Increase for more history, decrease to save tokens.">Max Entries</FieldLabel>
                        <input type="number" min={1} max={50} value={src.limit ?? 5}
                          onChange={e => updateSrc({ limit: parseInt(e.target.value) || 5 })}
                          className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs font-mono" />
                      </div>
                    </div>
                  )}
                  {src.type === 'pre_llm' && (
                    <div className="ml-1">
                      <FieldLabel hint="The 'id' field of a specific tool call or RAG config to inject. Leave blank to inject ALL pre-LLM results (tool calls + RAG) into this context source.">Result ID (blank = all pre-LLM results)</FieldLabel>
                      <Input value={src.result_id ?? ''} placeholder="e.g. search_call (matches tool call id)"
                        className="text-xs w-full"
                        onChange={e => updateSrc({ result_id: e.target.value || undefined })} />
                      {!(node.pre_llm?.tool_calls?.length) && !node.pre_llm?.rag?.enabled && (
                        <p className="text-[10px] text-amber-500 mt-1 flex items-center gap-1">
                          <i className="fas fa-triangle-exclamation"></i>
                          No Pre-LLM steps configured yet — add Tool Calls or RAG above.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            {/* Add source + inject_as row */}
            <div className="flex items-center gap-3 flex-wrap">
              <button onClick={() => {
                const sources = [...(node.context?.sources ?? []), { type: 'previous_node' as ContextSourceType }];
                onChange({ ...node, context: { ...node.context, sources } });
              }} className="text-xs px-2.5 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 rounded-lg transition-colors">
                + Add Source
              </button>
              <div className="flex items-center gap-2 ml-auto">
                <span className="text-[10px] text-slate-400 uppercase tracking-widest">inject as</span>
                <Select value={node.context?.inject_as ?? 'user'}
                  onChange={e => onChange({ ...node, context: { ...node.context, inject_as: e.target.value as 'system' | 'user' } })}
                  className="text-xs py-1">
                  <option value="user">user message (recommended for grounding)</option>
                  <option value="system">system message (higher authority)</option>
                </Select>
              </div>
            </div>

            {/* Synthesis — visible when 2+ sources */}
            {(node.context?.sources ?? []).length >= 1 && (
              <div className="border-t border-slate-100 pt-3 mt-1">
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                  <i className="fas fa-code-merge text-violet-400"></i>
                  Multi-Source Synthesis
                  <Tooltip text={[
                    "When this node has 2 or more context sources, synthesis controls how they are combined before reaching the LLM.",
                    "",
                    "concatenate (default): Each source is injected as a separate labelled block. Safe, transparent, and easy to debug.",
                    "",
                    "structured: All chunks merged into a single numbered message under '--- Consolidated Context ---'. Good for report-style context.",
                    "",
                    "summarize: All chunks prefixed with a synthesis instruction so the LLM consolidates them silently before answering. Best for complex multi-source reasoning. You can customize the instruction prompt.",
                  ].join("\n")}>
                    <span className="text-slate-300 hover:text-violet-400 cursor-help"><i className="fas fa-circle-info text-[10px]"></i></span>
                  </Tooltip>
                </p>
                <div className="space-y-2">
                  <div className="flex items-center gap-3">
                    <span className="text-[10px] text-slate-400 w-16 flex-shrink-0">Strategy</span>
                    <Select
                      value={node.context?.synthesis?.strategy ?? 'concatenate'}
                      onChange={e => onChange({ ...node, context: { ...node.context, synthesis: { ...node.context?.synthesis, strategy: e.target.value as SynthesisStrategy } } })}
                      className="flex-1 text-xs py-1">
                      <option value="concatenate">concatenate — separate labelled blocks (default)</option>
                      <option value="structured">structured — single merged message with numbered sources</option>
                      <option value="summarize">summarize — LLM consolidates via synthesis instruction</option>
                    </Select>
                  </div>
                  {node.context?.synthesis?.strategy === 'summarize' && (
                    <div>
                      <FieldLabel hint="Custom instruction prepended to the combined context. The LLM uses this to synthesize sources before answering. Leave blank for the default instruction.">Custom Synthesis Prompt (optional)</FieldLabel>
                      <textarea
                        value={node.context?.synthesis?.prompt_template ?? ''}
                        onChange={e => onChange({ ...node, context: { ...node.context, synthesis: { ...node.context?.synthesis, prompt_template: e.target.value || undefined } } })}
                        placeholder="e.g. Review the sources below and extract the most relevant facts before answering. Prioritize the RAG results over memory."
                        rows={3}
                        className="w-full px-2.5 py-2 border border-slate-200 rounded-lg text-xs font-mono resize-none focus:outline-none focus:ring-2 focus:ring-violet-300"
                      />
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── Context / Input Guardrails ─────────────────────────────── */}
            <div className="border-t border-slate-100 pt-3 mt-1">
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2.5 flex items-center gap-1.5">
                <i className="fas fa-shield-halved text-amber-400"></i>
                Context Input Guardrails
                <Tooltip text="These guardrails are applied to the assembled context BEFORE it reaches the LLM. They protect against prompt injection, credential leakage, PII entering external models, oversized context windows, and more.">
                  <span className="text-slate-300 hover:text-amber-400 cursor-help"><i className="fas fa-circle-info text-[10px]"></i></span>
                </Tooltip>
              </p>
              <div className="space-y-2">
                {([
                  { key: 'pii',              label: 'PII on Input',            desc: 'Redact emails, phones, SSNs before sending to LLM', defaultAction: 'redact' as GuardrailAction, hasAction: true },
                  { key: 'prompt_injection', label: 'Prompt Injection',        desc: 'Block jailbreaks / "ignore previous instructions"', defaultAction: 'block' as GuardrailAction, hasAction: true },
                  { key: 'secrets_detection',label: 'Secrets / Credentials',   desc: 'API keys, Bearer tokens, private keys, JWTs', defaultAction: 'block' as GuardrailAction, hasAction: true },
                  { key: 'profanity',        label: 'Profanity Filter',         desc: 'Filter offensive language in user-sourced context', defaultAction: 'redact' as GuardrailAction, hasAction: true },
                  { key: 'data_classification', label: 'Data Classification',  desc: 'Block CONFIDENTIAL / SECRET / RESTRICTED markers', defaultAction: 'block' as GuardrailAction, hasAction: true },
                  { key: 'encoding_sanitization', label: 'Encoding Sanitization', desc: 'Strip HTML tags, null bytes, control characters', defaultAction: null, hasAction: false },
                ] as const).map(({ key, label, desc, defaultAction, hasAction }) => {
                  const ig = node.context?.input_guardrails as any ?? {};
                  const cfg = ig[key] as any;
                  const isEnabled = !!cfg?.enabled;
                  const toggle = () => {
                    const updated = { ...ig, [key]: { ...cfg, enabled: !isEnabled, ...(defaultAction ? { action: defaultAction } : {}) } };
                    onChange({ ...node, context: { ...node.context, input_guardrails: updated } });
                  };
                  const setAction = (action: GuardrailAction) => {
                    onChange({ ...node, context: { ...node.context, input_guardrails: { ...ig, [key]: { ...cfg, enabled: true, action } } } });
                  };
                  return (
                    <div key={key} className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg border transition-all text-xs ${isEnabled ? 'bg-amber-50 border-amber-200' : 'bg-slate-50 border-slate-200'}`}>
                      <label className="flex items-center gap-2 cursor-pointer flex-1 min-w-0">
                        <input type="checkbox" checked={isEnabled} onChange={toggle} className="w-3.5 h-3.5 rounded flex-shrink-0" />
                        <div className="min-w-0">
                          <p className={`font-bold truncate ${isEnabled ? 'text-amber-700' : 'text-slate-500'}`}>{label}</p>
                          <p className="text-[10px] text-slate-400 truncate">{desc}</p>
                        </div>
                      </label>
                      {isEnabled && hasAction && (
                        <Select value={cfg?.action ?? defaultAction}
                          onChange={e => setAction(e.target.value as GuardrailAction)}
                          className="w-20 flex-shrink-0 text-[10px] py-0.5">
                          <option value="block">block</option>
                          <option value="redact">redact</option>
                          <option value="approve">approve</option>
                        </Select>
                      )}
                    </div>
                  );
                })}

                {/* Context Length */}
                {(() => {
                  const ig = node.context?.input_guardrails as any ?? {};
                  const cl = ig.context_length as any ?? {};
                  return (
                    <div className={`px-2.5 py-2 rounded-lg border transition-all text-xs ${cl.enabled ? 'bg-amber-50 border-amber-200' : 'bg-slate-50 border-slate-200'}`}>
                      <div className="flex items-center gap-2.5 mb-2">
                        <label className="flex items-center gap-2 cursor-pointer flex-1">
                          <input type="checkbox" checked={!!cl.enabled}
                            onChange={e => onChange({ ...node, context: { ...node.context, input_guardrails: { ...ig, context_length: { ...cl, enabled: e.target.checked } } } })}
                            className="w-3.5 h-3.5 rounded flex-shrink-0" />
                          <div>
                            <p className={`font-bold ${cl.enabled ? 'text-amber-700' : 'text-slate-500'}`}>Context Length Limit</p>
                            <p className="text-[10px] text-slate-400">Cap context size to prevent token budget overrun</p>
                          </div>
                        </label>
                      </div>
                      {cl.enabled && (
                        <div className="flex gap-2 items-center ml-5">
                          <div className="flex items-center gap-1.5 flex-1">
                            <span className="text-[10px] text-slate-400 flex-shrink-0">Max chars</span>
                            <input type="number" min={500} max={200000} step={500}
                              value={cl.max_chars ?? 8000}
                              onChange={e => onChange({ ...node, context: { ...node.context, input_guardrails: { ...ig, context_length: { ...cl, max_chars: parseInt(e.target.value) || 8000 } } } })}
                              className="w-24 px-2 py-1 border border-slate-200 rounded text-[11px] font-mono" />
                          </div>
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] text-slate-400 flex-shrink-0">On exceed</span>
                            <Select value={cl.on_exceed ?? 'truncate'}
                              onChange={e => onChange({ ...node, context: { ...node.context, input_guardrails: { ...ig, context_length: { ...cl, on_exceed: e.target.value as ContextLengthStrategy } } } })}
                              className="text-[10px] py-0.5 w-28">
                              <option value="truncate">truncate</option>
                              <option value="summarize">summarize</option>
                              <option value="error">error (block)</option>
                            </Select>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })()}

                {/* Language enforcement */}
                {(() => {
                  const ig = node.context?.input_guardrails as any ?? {};
                  const le = ig.language_enforcement as any ?? {};
                  return (
                    <div className={`px-2.5 py-2 rounded-lg border transition-all text-xs ${le.enabled ? 'bg-amber-50 border-amber-200' : 'bg-slate-50 border-slate-200'}`}>
                      <div className="flex items-center gap-2.5 mb-2">
                        <label className="flex items-center gap-2 cursor-pointer flex-1">
                          <input type="checkbox" checked={!!le.enabled}
                            onChange={e => onChange({ ...node, context: { ...node.context, input_guardrails: { ...ig, language_enforcement: { ...le, enabled: e.target.checked } } } })}
                            className="w-3.5 h-3.5 rounded flex-shrink-0" />
                          <div>
                            <p className={`font-bold ${le.enabled ? 'text-amber-700' : 'text-slate-500'}`}>Language Enforcement</p>
                            <p className="text-[10px] text-slate-400">Reject context not in the expected language</p>
                          </div>
                        </label>
                      </div>
                      {le.enabled && (
                        <div className="flex gap-2 items-center ml-5">
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] text-slate-400">Expected</span>
                            <Select value={le.expected_language ?? 'en'}
                              onChange={e => onChange({ ...node, context: { ...node.context, input_guardrails: { ...ig, language_enforcement: { ...le, expected_language: e.target.value } } } })}
                              className="text-[10px] py-0.5 w-24">
                              <option value="en">English (en)</option>
                              <option value="fr">French (fr)</option>
                              <option value="de">German (de)</option>
                              <option value="es">Spanish (es)</option>
                              <option value="zh">Chinese (zh)</option>
                            </Select>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] text-slate-400">Action</span>
                            <Select value={le.action ?? 'block'}
                              onChange={e => onChange({ ...node, context: { ...node.context, input_guardrails: { ...ig, language_enforcement: { ...le, action: e.target.value } } } })}
                              className="text-[10px] py-0.5 w-20">
                              <option value="block">block</option>
                              <option value="approve">log only</option>
                            </Select>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            </div>
          </div>
        </NodeSubSection>
      )}

      {/* ── Output Schema (agent only) ───────────────────────────────────────── */}
      {node.type === 'agent' && (
        <NodeSubSection icon="fa-file-code" title="Output Schema"
          hint="Define the expected output format from the LLM. JSON format enables field validation. state_key writes the result into workflow state.">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <FieldLabel hint="Expected output format">Format</FieldLabel>
              <Select value={node.output_schema?.format ?? 'text'}
                onChange={e => onChange({ ...node, output_schema: { ...node.output_schema, format: e.target.value as OutputFormat } })}>
                <option value="text">text (freeform)</option>
                <option value="json">json (validated)</option>
                <option value="markdown">markdown</option>
              </Select>
            </div>
            <div>
              <FieldLabel hint="Write the LLM output to this state variable (must match state_schema key)">State Key</FieldLabel>
              <Select value={node.output_schema?.state_key ?? ''}
                onChange={e => onChange({ ...node, output_schema: { ...node.output_schema, state_key: e.target.value || undefined } })}>
                <option value="">— none —</option>
                {stateKeys.map(k => <option key={k} value={k}>{k}</option>)}
              </Select>
            </div>
          </div>
          {node.output_schema?.format === 'json' && (
            <div>
              <FieldLabel hint="Comma-separated field names that must be present in the JSON output">Required Fields</FieldLabel>
              <Input value={(node.output_schema?.required_fields ?? []).join(', ')}
                onChange={e => onChange({ ...node, output_schema: { ...node.output_schema, required_fields: e.target.value.split(',').map(s => s.trim()).filter(Boolean) } })}
                placeholder="e.g. summary, confidence, sources" />
            </div>
          )}
        </NodeSubSection>
      )}

      {/* ── Validation (agent only) ──────────────────────────────────────────── */}
      {node.type === 'agent' && (
        <NodeSubSection icon="fa-circle-check" title="Output Validation"
          hint="Add rules to validate the LLM output. Rules are evaluated after output_schema parsing. on_failure controls what happens when a rule fails.">
          <div className="flex items-center gap-4 mb-3">
            <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
              <input type="checkbox" checked={!!node.validation?.enabled}
                onChange={e => onChange({ ...node, validation: { ...node.validation, enabled: e.target.checked } })}
                className="w-4 h-4 rounded" />
              Enable validation
            </label>
            {node.validation?.enabled && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400">On failure:</span>
                <Select value={node.validation?.on_failure ?? 'warn'}
                  onChange={e => onChange({ ...node, validation: { ...node.validation, on_failure: e.target.value as OnFailure } })}
                  className="text-xs py-1">
                  <option value="warn">warn (continue)</option>
                  <option value="retry">retry node</option>
                  <option value="error">halt workflow</option>
                </Select>
              </div>
            )}
          </div>
          {node.validation?.enabled && (
            <div className="space-y-2">
              {(node.validation?.rules ?? []).map((rule, ri) => (
                <div key={ri} className="flex gap-2 items-center">
                  <Select value={rule.field}
                    onChange={e => {
                      const rules = [...(node.validation?.rules ?? [])];
                      rules[ri] = { ...rule, field: e.target.value };
                      onChange({ ...node, validation: { ...node.validation, rules } });
                    }} className="w-32 flex-shrink-0 text-xs">
                    <option value="">field…</option>
                    {(node.output_schema?.required_fields ?? []).map(f => <option key={f} value={f}>{f}</option>)}
                    {stateKeys.map(k => <option key={k} value={k}>{k}</option>)}
                  </Select>
                  <Select value={rule.operator}
                    onChange={e => {
                      const rules = [...(node.validation?.rules ?? [])];
                      rules[ri] = { ...rule, operator: e.target.value as ValidationRule['operator'] };
                      onChange({ ...node, validation: { ...node.validation, rules } });
                    }} className="w-16 flex-shrink-0 text-xs">
                    {['>=','<=','>','<','==','!='].map(op => <option key={op} value={op}>{op}</option>)}
                  </Select>
                  <Input value={String(rule.value ?? '')} placeholder="value"
                    onChange={e => {
                      const rules = [...(node.validation?.rules ?? [])];
                      rules[ri] = { ...rule, value: e.target.value };
                      onChange({ ...node, validation: { ...node.validation, rules } });
                    }} className="flex-1 text-xs" />
                  <button onClick={() => {
                    onChange({ ...node, validation: { ...node.validation, rules: (node.validation?.rules ?? []).filter((_, i) => i !== ri) } });
                  }} className="text-slate-300 hover:text-rose-500 flex-shrink-0"><i className="fas fa-xmark text-xs"></i></button>
                </div>
              ))}
              <button onClick={() => {
                const rules = [...(node.validation?.rules ?? []), { field: '', operator: '>=' as const, value: '' }];
                onChange({ ...node, validation: { ...node.validation, rules } });
              }} className="text-xs px-2.5 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 rounded-lg transition-colors">
                + Add Rule
              </button>
            </div>
          )}
        </NodeSubSection>
      )}

      {/* ── Guardrails (agent only) ──────────────────────────────────────────── */}
      {node.type === 'agent' && (
        <NodeSubSection icon="fa-shield-halved" title="Safety Guardrails"
          hint="Per-node content safety. Each check runs on the LLM output before it enters the workflow state. block=halt, redact=mask sensitive content, approve=log only.">
          <div className="space-y-2.5">
            {([
              { key: 'pii',             label: 'PII Detection',         desc: 'Emails, phones, SSNs, credit cards, IPs', defaultAction: 'redact' as GuardrailAction },
              { key: 'harmful_content', label: 'Harmful Content',       desc: 'Dangerous instructions, weapon/drug synthesis', defaultAction: 'block' as GuardrailAction },
              { key: 'self_harm',       label: 'Self-Harm Content',     desc: 'Suicide, self-injury, related language', defaultAction: 'block' as GuardrailAction },
              { key: 'hate_speech',     label: 'Hate Speech',           desc: 'Hate speech, ethnic/racial incitement', defaultAction: 'block' as GuardrailAction },
              { key: 'regulated_advice',label: 'Regulated Advice',      desc: 'Medical, legal, or financial advice', defaultAction: 'block' as GuardrailAction },
            ] as const).map(({ key, label, desc, defaultAction }) => {
              const cfg = (node.guardrails as any)?.[key] as GuardrailCheck | undefined;
              const isEnabled = !!cfg?.enabled;
              const toggleEnabled = () => {
                const g = node.guardrails ?? {};
                onChange({ ...node, guardrails: {
                  ...g,
                  [key]: isEnabled
                    ? { enabled: false, action: defaultAction }
                    : { enabled: true,  action: defaultAction },
                }});
              };
              const setAction = (action: GuardrailAction) => {
                const g = node.guardrails ?? {};
                onChange({ ...node, guardrails: { ...g, [key]: { ...cfg, enabled: true, action } } });
              };
              return (
                <div key={key} className={`flex items-center gap-3 px-3 py-2.5 rounded-xl border transition-all ${isEnabled ? 'bg-rose-50 border-rose-200' : 'bg-slate-50 border-slate-200'}`}>
                  <label className="flex items-center gap-2 cursor-pointer flex-1 min-w-0">
                    <input type="checkbox" checked={isEnabled} onChange={toggleEnabled}
                      className="w-4 h-4 rounded flex-shrink-0" />
                    <div className="min-w-0">
                      <p className={`text-xs font-bold ${isEnabled ? 'text-rose-700' : 'text-slate-600'}`}>{label}</p>
                      <p className="text-[10px] text-slate-400 truncate">{desc}</p>
                    </div>
                  </label>
                  {isEnabled && (
                    <Select value={cfg?.action ?? defaultAction} onChange={e => setAction(e.target.value as GuardrailAction)}
                      className="w-24 flex-shrink-0 text-xs py-1">
                      <option value="block">block</option>
                      <option value="redact">redact</option>
                      <option value="approve">approve</option>
                    </Select>
                  )}
                  {!isEnabled && (
                    <span className="text-[10px] text-slate-300 flex-shrink-0 w-24 text-center">off</span>
                  )}
                </div>
              );
            })}
            {/* Regulated advice: sub-checks */}
            {node.guardrails?.regulated_advice?.enabled && (
              <div className="ml-4 flex gap-3 flex-wrap">
                <p className="text-[10px] text-slate-400 uppercase tracking-widest w-full">Regulated categories:</p>
                {(['medical','legal','financial'] as const).map(cat => {
                  const checks = node.guardrails?.regulated_advice?.checks ?? ['medical','legal','financial'];
                  const active = checks.includes(cat);
                  return (
                    <label key={cat} className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer">
                      <input type="checkbox" checked={active}
                        onChange={() => {
                          const g = node.guardrails ?? {};
                          const ra = (g.regulated_advice ?? { enabled: true, action: 'block' as GuardrailAction });
                          const next = active ? checks.filter(c => c !== cat) : [...checks, cat];
                          onChange({ ...node, guardrails: { ...g, regulated_advice: { ...ra, checks: next } } });
                        }} className="w-3.5 h-3.5 rounded" />
                      {cat}
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        </NodeSubSection>
      )}
    </div>
  );
};

// ── Workflow Graph Preview (pure SVG, no external deps) ────────────────────────

const GNODE_W = 148;
const GNODE_H = 56;   // taller to fit capability badges
const RANK_GAP = 80;
const COL_GAP = 16;
const GPAD = 24;

const GNODE_COLORS: Record<string, { fill: string; stroke: string; text: string; badge: string }> = {
  agent:      { fill: '#eef2ff', stroke: '#6366f1', text: '#4338ca', badge: '#c7d2fe' },
  tool_node:  { fill: '#f0fdfa', stroke: '#14b8a6', text: '#0f766e', badge: '#99f6e4' },
  conditional:{ fill: '#fffbeb', stroke: '#f59e0b', text: '#b45309', badge: '#fde68a' },
  human_node: { fill: '#fff1f2', stroke: '#f43f5e', text: '#be123c', badge: '#fecdd3' },
  END:        { fill: '#f1f5f9', stroke: '#94a3b8', text: '#475569', badge: '#e2e8f0' },
  default:    { fill: '#f8fafc', stroke: '#cbd5e1', text: '#64748b', badge: '#e2e8f0' },
};

interface GNode {
  id: string; type: string; x: number; y: number;
  toolCount: number;    // number of tools[]
  hasPreLlmTools: boolean;  // pre_llm.tool_calls
  hasRag: boolean;      // pre_llm.rag.enabled
  hasRouting: boolean;  // routing_logic.length > 0
  hasGuardrails: boolean;
  hasCheckpoint: boolean;
}
interface GEdge { from: string; to: string; condition?: string; isRouting: boolean; }

function buildGraphLayout(nodes: NodeConfig[], edges: EdgeConfig[]) {
  if (!nodes.length) return null;
  const allIds = nodes.map(n => n.id);

  // Determine if any path ends at END
  const anyEnd =
    nodes.some(n => n.next === 'END' || n.routing_logic?.some(r => r.next === 'END')) ||
    edges.some(e => e.to === 'END');
  const displayIds = [...allIds, ...(anyEnd ? ['END'] : [])];

  // Build successor map (for BFS rank assignment)
  const succs: Record<string, string[]> = {};
  displayIds.forEach(id => { succs[id] = []; });
  const addS = (from: string, to: string) => {
    const t = to === 'END' ? (anyEnd ? 'END' : null) : to;
    if (!t || !(from in succs) || succs[from].includes(t)) return;
    succs[from].push(t);
  };
  edges.forEach(e => e.from && e.to && addS(e.from, e.to));
  nodes.forEach(n => {
    if (n.next) addS(n.id, n.next);
    n.routing_logic?.forEach(r => r.next && addS(n.id, r.next));
  });

  // BFS rank from first node
  const rank: Record<string, number> = { [displayIds[0]]: 0 };
  const q = [displayIds[0]];
  while (q.length) {
    const cur = q.shift()!;
    succs[cur]?.forEach(nxt => {
      if (rank[nxt] === undefined) { rank[nxt] = rank[cur] + 1; q.push(nxt); }
    });
  }
  const maxVisited = Math.max(0, ...Object.values(rank));
  displayIds.forEach(id => { if (rank[id] === undefined) rank[id] = maxVisited + 1; });

  // Group by rank
  const groups: Record<number, string[]> = {};
  displayIds.forEach(id => {
    const r = rank[id];
    if (!groups[r]) groups[r] = [];
    groups[r].push(id);
  });
  const maxRank = Math.max(...Object.keys(groups).map(Number));
  const maxCols = Math.max(...Object.values(groups).map(g => g.length));

  const svgW = Math.max(230, maxCols * (GNODE_W + COL_GAP) - COL_GAP + GPAD * 2);
  const svgH = GPAD + (maxRank + 1) * (GNODE_H + RANK_GAP) - RANK_GAP + GNODE_H + GPAD;

  // Compute node positions (centered within each rank row)
  const pos: Record<string, { x: number; y: number }> = {};
  Object.entries(groups).forEach(([rStr, ids]) => {
    const r = Number(rStr);
    const rowW = ids.length * (GNODE_W + COL_GAP) - COL_GAP;
    const startX = (svgW - rowW) / 2;
    const y = GPAD + r * (GNODE_H + RANK_GAP);
    ids.forEach((id, i) => { pos[id] = { x: startX + i * (GNODE_W + COL_GAP), y }; });
  });

  // Collect drawable edges (deduplicated, track if conditional/routing)
  const seen = new Set<string>();
  const drawEdges: GEdge[] = [];
  const addDE = (from: string, to: string, condition?: string, isRouting = false) => {
    const t = to === 'END' && anyEnd ? 'END' : to;
    const key = `${from}→${t}`;
    if (!seen.has(key) && pos[from] && pos[t]) {
      seen.add(key);
      drawEdges.push({ from, to: t, condition, isRouting: isRouting || !!condition });
    }
  };
  edges.forEach(e => e.from && e.to && addDE(e.from, e.to, e.condition || undefined, !!e.condition));
  nodes.forEach(n => {
    if (n.next) addDE(n.id, n.next);
    n.routing_logic?.forEach(r => r.next && addDE(n.id, r.next, r.condition, true));
  });

  const gnodes: GNode[] = displayIds
    .filter(id => pos[id])
    .map(id => {
      const nc = nodes.find(n => n.id === id);
      return {
        id, ...pos[id],
        type: id === 'END' ? 'END' : (nc?.type ?? 'agent'),
        toolCount: nc?.tools?.length ?? 0,
        hasPreLlmTools: (nc?.pre_llm?.tool_calls?.length ?? 0) > 0,
        hasRag: !!(nc?.pre_llm?.rag?.enabled),
        hasRouting: (nc?.routing_logic?.length ?? 0) > 0,
        hasGuardrails: !!(nc?.guardrails && Object.keys(nc.guardrails).length > 0),
        hasCheckpoint: !!nc?.checkpoint,
      };
    });

  return { gnodes, drawEdges, svgW, svgH };
}

const WorkflowGraphPreview: React.FC<{
  nodes: NodeConfig[];
  edges: EdgeConfig[];
  selectedNodeId?: string | null;
  onNodeClick?: (id: string) => void;
}> = ({ nodes, edges, selectedNodeId, onNodeClick }) => {
  const layout = useMemo(() => buildGraphLayout(nodes, edges), [nodes, edges]);

  if (!layout) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center text-slate-400">
        <i className="fas fa-circle-nodes text-3xl mb-3 text-slate-200"></i>
        <p className="text-xs">Add nodes to see<br />the workflow graph</p>
      </div>
    );
  }

  const { gnodes, drawEdges, svgW, svgH } = layout;
  const cx = (n: GNode) => n.x + GNODE_W / 2;
  const bot = (n: GNode) => n.y + GNODE_H;
  const top = (n: GNode) => n.y;

  return (
    <div className="overflow-auto rounded-xl bg-white border border-slate-200">
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        width={svgW}
        height={svgH}
        xmlns="http://www.w3.org/2000/svg"
        style={{ display: 'block', maxWidth: '100%' }}
      >
        <defs>
          <marker id="gph-arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#94a3b8" />
          </marker>
          <marker id="gph-arrow-sel" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#6366f1" />
          </marker>
          <marker id="gph-arrow-cond" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#f59e0b" />
          </marker>
        </defs>

        {/* Edges */}
        {drawEdges.map((e, i) => {
          const src = gnodes.find(n => n.id === e.from);
          const dst = gnodes.find(n => n.id === e.to);
          if (!src || !dst) return null;
          const x1 = cx(src), y1 = bot(src);
          const x2 = cx(dst), y2 = top(dst);
          const dy = Math.abs(y2 - y1) * 0.45;
          const path = `M ${x1} ${y1} C ${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`;
          const isSel = e.from === selectedNodeId || e.to === selectedNodeId;
          const isRouting = e.isRouting;
          const edgeColor = isSel ? '#6366f1' : isRouting ? '#f59e0b' : '#cbd5e1';
          const markerId = isSel ? 'gph-arrow-sel' : isRouting ? 'gph-arrow-cond' : 'gph-arrow';
          const midX = (x1 + x2) / 2;
          const midY = (y1 + y2) / 2;

          // Truncate condition smartly — show up to 28 chars
          const condLabel = e.condition
            ? (e.condition.length > 26 ? e.condition.slice(0, 24) + '…' : e.condition)
            : null;
          const condW = condLabel ? Math.min(condLabel.length * 5.5 + 12, 140) : 0;

          return (
            <g key={i}>
              <path
                d={path}
                fill="none"
                stroke={edgeColor}
                strokeWidth={isSel ? 2.5 : isRouting ? 1.5 : 1.5}
                strokeDasharray={isRouting ? '5 3' : undefined}
                markerEnd={`url(#${markerId})`}
                opacity={isSel ? 1 : 0.8}
              />
              {condLabel && (
                <g>
                  {/* Pill background for condition text */}
                  <rect
                    x={midX - condW / 2} y={midY - 10}
                    width={condW} height={14}
                    rx={7}
                    fill={isSel ? '#eef2ff' : '#fefce8'}
                    stroke={isSel ? '#a5b4fc' : '#fde68a'}
                    strokeWidth={1}
                  />
                  <text
                    x={midX} y={midY}
                    textAnchor="middle"
                    fontSize="8"
                    fill={isSel ? '#4338ca' : '#92400e'}
                    fontFamily="ui-monospace, monospace"
                    fontWeight="500"
                    style={{ userSelect: 'none' }}
                  >
                    {condLabel}
                  </text>
                </g>
              )}
            </g>
          );
        })}

        {/* Nodes */}
        {gnodes.map(n => {
          const colors = GNODE_COLORS[n.type] ?? GNODE_COLORS.default;
          const isSel = n.id === selectedNodeId;
          const isEnd = n.id === 'END';

          // Capability badges: tool, pre-llm, rag, routing, guardrails, checkpoint
          const badges: Array<{ icon: string; label: string; color: string }> = [];
          if (!isEnd) {
            if (n.toolCount > 0)      badges.push({ icon: '⚙', label: `${n.toolCount}T`, color: '#0f766e' });
            if (n.hasPreLlmTools)     badges.push({ icon: '⚡', label: 'pre', color: '#7c3aed' });
            if (n.hasRag)             badges.push({ icon: '🔍', label: 'rag', color: '#0369a1' });
            if (n.hasRouting)         badges.push({ icon: '⇶', label: 'cond', color: '#b45309' });
            if (n.hasGuardrails)      badges.push({ icon: '🛡', label: 'guard', color: '#be123c' });
            if (n.hasCheckpoint)      badges.push({ icon: '⏸', label: 'ckpt', color: '#b45309' });
          }

          const badgeAreaY = n.y + GNODE_H - 17;

          return (
            <g
              key={n.id}
              onClick={() => !isEnd && onNodeClick?.(n.id)}
              style={{ cursor: isEnd ? 'default' : 'pointer' }}
            >
              {/* Node body */}
              <rect
                x={n.x} y={n.y}
                width={GNODE_W} height={GNODE_H}
                rx={isEnd ? GNODE_H / 2 : 9}
                fill={colors.fill}
                stroke={isSel ? '#4f46e5' : colors.stroke}
                strokeWidth={isSel ? 2.5 : 1.5}
                filter={isSel ? 'drop-shadow(0 0 6px rgba(99,102,241,0.4))' : undefined}
              />

              {isEnd ? (
                <text
                  x={n.x + GNODE_W / 2} y={n.y + GNODE_H / 2 + 4}
                  textAnchor="middle" fontSize="12" fontWeight="700"
                  fill={colors.text} fontFamily="ui-sans-serif, system-ui, sans-serif"
                  style={{ userSelect: 'none' }}
                >END</text>
              ) : (
                <>
                  {/* Node label */}
                  <text
                    x={n.x + GNODE_W / 2} y={n.y + 16}
                    textAnchor="middle" fontSize="11.5" fontWeight="700"
                    fill={colors.text} fontFamily="ui-sans-serif, system-ui, sans-serif"
                    style={{ userSelect: 'none' }}
                  >
                    {n.id.length > 16 ? n.id.slice(0, 14) + '…' : n.id}
                  </text>

                  {/* Node type pill */}
                  <rect
                    x={n.x + GNODE_W / 2 - 26} y={n.y + 20}
                    width={52} height={12}
                    rx={6}
                    fill={colors.badge}
                  />
                  <text
                    x={n.x + GNODE_W / 2} y={n.y + 29.5}
                    textAnchor="middle" fontSize="7.5" fontWeight="600"
                    fill={colors.text} fontFamily="ui-sans-serif, system-ui, sans-serif"
                    style={{ userSelect: 'none' }}
                  >
                    {n.type}
                  </text>

                  {/* Capability badges row */}
                  {badges.length > 0 && (
                    <g>
                      {/* Separator line */}
                      <line
                        x1={n.x + 8} y1={badgeAreaY - 3}
                        x2={n.x + GNODE_W - 8} y2={badgeAreaY - 3}
                        stroke={colors.stroke} strokeWidth={0.5} opacity={0.3}
                      />
                      {badges.slice(0, 5).map((b, bi) => {
                        const bW = b.label.length * 5 + 14;
                        const totalW = badges.slice(0, 5).reduce((s, bb) => s + bb.label.length * 5 + 14 + 3, -3);
                        const startBX = n.x + (GNODE_W - Math.min(totalW, GNODE_W - 8)) / 2;
                        const prevW = badges.slice(0, bi).reduce((s, bb) => s + bb.label.length * 5 + 14 + 3, 0);
                        const bx = startBX + prevW;
                        return (
                          <g key={bi}>
                            <rect x={bx} y={badgeAreaY} width={bW} height={11} rx={5.5}
                              fill="white" stroke={b.color} strokeWidth={0.75} opacity={0.9} />
                            <text x={bx + bW / 2} y={badgeAreaY + 7.5}
                              textAnchor="middle" fontSize="7" fontWeight="600"
                              fill={b.color} fontFamily="ui-monospace, monospace"
                              style={{ userSelect: 'none' }}>
                              {b.label}
                            </text>
                          </g>
                        );
                      })}
                    </g>
                  )}
                </>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
};

// ── Node detail rows (for full-page graph) ────────────────────────────────────

interface NodeRow { icon: string; text: string; color: string; }

function getNodeDetailRows(nc: NodeConfig): NodeRow[] {
  const rows: NodeRow[] = [];

  // LLM Config
  const llm = nc.llm_config;
  if (llm?.model || llm?.temperature !== undefined || llm?.max_tokens) {
    const p: string[] = [];
    if (llm.model) p.push(llm.model.split('/').pop()?.slice(0, 20) ?? llm.model.slice(0, 20));
    if (llm.temperature !== undefined) p.push(`T=${llm.temperature}`);
    if (llm.max_tokens) p.push(`${llm.max_tokens}tok`);
    if (p.length) rows.push({ icon: '🤖', text: p.join(' · '), color: '#7c3aed' });
  }

  // Tools
  if ((nc.tools?.length ?? 0) > 0) {
    const names = nc.tools!.slice(0, 3).join(', ') + (nc.tools!.length > 3 ? ` +${nc.tools!.length - 3}` : '');
    rows.push({ icon: '⚙', text: names, color: '#0f766e' });
  }

  // Memory Access
  if ((nc.memory_access?.length ?? 0) > 0) {
    const labels = nc.memory_access!.map(m => m === 'short_term' ? 'STM' : m === 'long_term' ? 'LTM' : m).join(' + ');
    rows.push({ icon: '💾', text: labels, color: '#0369a1' });
  }

  // Pre-LLM tool calls
  if ((nc.pre_llm?.tool_calls?.length ?? 0) > 0) {
    rows.push({ icon: '⚡', text: `pre: ${nc.pre_llm!.tool_calls!.length} tool call(s)`, color: '#7c3aed' });
  }

  // RAG
  if (nc.pre_llm?.rag?.enabled) {
    const r = nc.pre_llm.rag;
    const p = [r.provider ?? 'default'];
    if (r.top_k) p.push(`top-${r.top_k}`);
    rows.push({ icon: '🔍', text: `RAG: ${p.join(' ')}`, color: '#0369a1' });
  }

  // Context sources
  if ((nc.context?.sources?.length ?? 0) > 0) {
    const abbrev: Record<string, string> = { previous_node: 'prev', stm: 'STM', ltm: 'LTM', pre_llm: 'pre' };
    const types = [...new Set(nc.context!.sources!.map(s => abbrev[s.type] ?? s.type))].join('+');
    const strat = nc.context?.synthesis?.strategy ? ` (${nc.context.synthesis.strategy})` : '';
    rows.push({ icon: '📑', text: `ctx: ${types}${strat}`, color: '#475569' });
  }

  // Output schema
  if (nc.output_schema?.format || nc.output_schema?.state_key) {
    const p: string[] = [];
    if (nc.output_schema.format) p.push(nc.output_schema.format);
    if (nc.output_schema.state_key) p.push(`→ ${nc.output_schema.state_key}`);
    rows.push({ icon: '📋', text: p.join(' '), color: '#0f766e' });
  }

  // Validation
  const vRules = (nc.validation?.rules?.length ?? 0) + (nc.output_schema?.validation?.rules?.length ?? 0);
  if (nc.validation?.enabled || vRules > 0) {
    rows.push({ icon: '✅', text: `validate: ${vRules} rule${vRules !== 1 ? 's' : ''}`, color: '#059669' });
  }

  // Output safety guardrails
  const safeGuards = Object.entries(nc.guardrails ?? {})
    .filter(([, v]) => (v as any)?.enabled)
    .map(([k]) => ({ pii: 'PII', harmful_content: 'harm', hate_speech: 'hate', self_harm: 'self', regulated_advice: 'reg' }[k] ?? k.slice(0, 5)));
  if (safeGuards.length > 0) {
    rows.push({ icon: '🛡', text: `out: ${safeGuards.join(', ')}`, color: '#be123c' });
  }

  // Input guardrails (from context)
  const inGuards = Object.entries(nc.context?.input_guardrails ?? {})
    .filter(([, v]) => (v as any)?.enabled)
    .map(([k]) => ({ pii: 'PII', prompt_injection: 'inj', secrets_detection: 'sec', profanity: 'prof', context_length: 'len' }[k] ?? k.slice(0, 4)));
  if (inGuards.length > 0) {
    rows.push({ icon: '🔒', text: `in-guards: ${inGuards.join(', ')}`, color: '#be123c' });
  }

  // Routing logic
  if ((nc.routing_logic?.length ?? 0) > 0) {
    const targets = [...new Set(nc.routing_logic!.map(r => r.next))].slice(0, 3).join(', ');
    rows.push({ icon: '⇶', text: `${nc.routing_logic!.length} route(s) → ${targets}`, color: '#b45309' });
  }

  // Checkpoint
  if (nc.checkpoint) {
    rows.push({ icon: '⏸', text: 'human-in-loop checkpoint', color: '#b45309' });
  }

  return rows;
}

// ── Full-page graph layout constants ──────────────────────────────────────────

const FGNODE_W = 230;
const FGNODE_HDR = 34;   // header height (id label + type pill)
const FGNODE_ROW_H = 14; // height per detail row
const FGNODE_VPAD = 7;   // bottom padding
const FGNODE_MIN = 36;   // min height for END node
const FRANK_GAP = 100;
const FCOL_GAP = 32;
const FGPAD = 36;

function fNodeHeight(rows: NodeRow[]): number {
  if (rows.length === 0) return FGNODE_MIN;
  return FGNODE_HDR + 4 + rows.length * FGNODE_ROW_H + FGNODE_VPAD;
}

interface FGNode { id: string; type: string; x: number; y: number; height: number; rows: NodeRow[]; }
interface FGEdge { from: string; to: string; condition?: string; isRouting: boolean; }

function buildFullPageLayout(nodes: NodeConfig[], edges: EdgeConfig[]) {
  if (!nodes.length) return null;
  const allIds = nodes.map(n => n.id);
  const nodeRowsMap: Record<string, NodeRow[]> = {};
  nodes.forEach(n => { nodeRowsMap[n.id] = getNodeDetailRows(n); });

  const anyEnd =
    nodes.some(n => n.next === 'END' || n.routing_logic?.some(r => r.next === 'END')) ||
    edges.some(e => e.to === 'END');
  const displayIds = [...allIds, ...(anyEnd ? ['END'] : [])];

  const succs: Record<string, string[]> = {};
  displayIds.forEach(id => { succs[id] = []; });
  const addS = (from: string, to: string) => {
    const t = to === 'END' ? (anyEnd ? 'END' : null) : to;
    if (!t || !(from in succs) || succs[from].includes(t)) return;
    succs[from].push(t);
  };
  edges.forEach(e => e.from && e.to && addS(e.from, e.to));
  nodes.forEach(n => {
    if (n.next) addS(n.id, n.next);
    n.routing_logic?.forEach(r => r.next && addS(n.id, r.next));
  });

  const rank: Record<string, number> = { [displayIds[0]]: 0 };
  const q = [displayIds[0]];
  while (q.length) {
    const cur = q.shift()!;
    succs[cur]?.forEach(nxt => {
      if (rank[nxt] === undefined) { rank[nxt] = rank[cur] + 1; q.push(nxt); }
    });
  }
  const maxVisited = Math.max(0, ...Object.values(rank));
  displayIds.forEach(id => { if (rank[id] === undefined) rank[id] = maxVisited + 1; });

  const groups: Record<number, string[]> = {};
  displayIds.forEach(id => {
    const r = rank[id];
    if (!groups[r]) groups[r] = [];
    groups[r].push(id);
  });
  const maxRank = Math.max(...Object.keys(groups).map(Number));
  const maxCols = Math.max(...Object.values(groups).map(g => g.length));

  // Per-rank max heights → cumulative Y positions
  const rankMaxH: Record<number, number> = {};
  Object.entries(groups).forEach(([rStr, ids]) => {
    rankMaxH[Number(rStr)] = Math.max(...ids.map(id => fNodeHeight(nodeRowsMap[id] ?? [])));
  });
  const rankY: Record<number, number> = { 0: FGPAD };
  for (let r = 1; r <= maxRank; r++) {
    rankY[r] = rankY[r - 1] + rankMaxH[r - 1] + FRANK_GAP;
  }

  const svgW = Math.max(350, maxCols * (FGNODE_W + FCOL_GAP) - FCOL_GAP + FGPAD * 2);
  const svgH = rankY[maxRank] + (rankMaxH[maxRank] ?? FGNODE_MIN) + FGPAD;

  const pos: Record<string, { x: number; y: number }> = {};
  Object.entries(groups).forEach(([rStr, ids]) => {
    const r = Number(rStr);
    const rowW = ids.length * (FGNODE_W + FCOL_GAP) - FCOL_GAP;
    const startX = (svgW - rowW) / 2;
    ids.forEach((id, i) => { pos[id] = { x: startX + i * (FGNODE_W + FCOL_GAP), y: rankY[r] }; });
  });

  const seen = new Set<string>();
  const drawEdges: FGEdge[] = [];
  const addDE = (from: string, to: string, condition?: string, isRouting = false) => {
    const t = to === 'END' && anyEnd ? 'END' : to;
    const key = `${from}→${t}`;
    if (!seen.has(key) && pos[from] && pos[t]) {
      seen.add(key); drawEdges.push({ from, to: t, condition, isRouting: isRouting || !!condition });
    }
  };
  edges.forEach(e => e.from && e.to && addDE(e.from, e.to, e.condition, !!e.condition));
  nodes.forEach(n => {
    if (n.next) addDE(n.id, n.next);
    n.routing_logic?.forEach(r => r.next && addDE(n.id, r.next, r.condition, true));
  });

  const fgnodes: FGNode[] = displayIds
    .filter(id => pos[id])
    .map(id => ({
      id, ...pos[id],
      type: id === 'END' ? 'END' : (nodes.find(n => n.id === id)?.type ?? 'agent'),
      height: fNodeHeight(nodeRowsMap[id] ?? []),
      rows: nodeRowsMap[id] ?? [],
    }));

  return { fgnodes, drawEdges, svgW, svgH };
}

// ── Full-page graph SVG renderer ──────────────────────────────────────────────

const FullPageWorkflowGraph: React.FC<{ nodes: NodeConfig[]; edges: EdgeConfig[]; }> = ({ nodes, edges }) => {
  const layout = useMemo(() => buildFullPageLayout(nodes, edges), [nodes, edges]);
  if (!layout) return <div className="flex items-center justify-center py-20 text-slate-400">Add nodes to see the graph</div>;

  const { fgnodes, drawEdges, svgW, svgH } = layout;
  const fcx = (n: FGNode) => n.x + FGNODE_W / 2;
  const fbot = (n: FGNode) => n.y + n.height;

  return (
    <div className="overflow-auto rounded-xl bg-white border border-slate-200 shadow-sm">
      <svg viewBox={`0 0 ${svgW} ${svgH}`} width={svgW} height={svgH} xmlns="http://www.w3.org/2000/svg" style={{ display: 'block' }}>
        <defs>
          <marker id="fp-arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#94a3b8" />
          </marker>
          <marker id="fp-arrow-cond" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#f59e0b" />
          </marker>
        </defs>

        {/* Edges */}
        {drawEdges.map((e, i) => {
          const src = fgnodes.find(n => n.id === e.from);
          const dst = fgnodes.find(n => n.id === e.to);
          if (!src || !dst) return null;
          const x1 = fcx(src), y1 = fbot(src);
          const x2 = fcx(dst), y2 = dst.y;
          const dy = Math.abs(y2 - y1) * 0.5;
          const path = `M ${x1} ${y1} C ${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`;
          const edgeColor = e.isRouting ? '#f59e0b' : '#94a3b8';
          const midX = (x1 + x2) / 2, midY = (y1 + y2) / 2;
          const condLabel = e.condition
            ? (e.condition.length > 36 ? e.condition.slice(0, 34) + '…' : e.condition)
            : null;
          const condW = condLabel ? Math.min(condLabel.length * 6.2 + 18, 200) : 0;
          return (
            <g key={i}>
              <path d={path} fill="none" stroke={edgeColor} strokeWidth={1.5}
                strokeDasharray={e.isRouting ? '6 3' : undefined}
                markerEnd={`url(#${e.isRouting ? 'fp-arrow-cond' : 'fp-arrow'})`} opacity={0.85}
              />
              {condLabel && (
                <g>
                  <rect x={midX - condW / 2} y={midY - 10} width={condW} height={17} rx={8.5}
                    fill="#fefce8" stroke="#fde68a" strokeWidth={1} />
                  <text x={midX} y={midY + 2.5} textAnchor="middle" fontSize="9.5" fill="#92400e"
                    fontFamily="ui-monospace, monospace" fontWeight="500" style={{ userSelect: 'none' }}>
                    {condLabel}
                  </text>
                </g>
              )}
            </g>
          );
        })}

        {/* Nodes */}
        {fgnodes.map(n => {
          const colors = GNODE_COLORS[n.type] ?? GNODE_COLORS.default;
          const isEnd = n.id === 'END';
          const typeText = n.type;
          const tW = typeText.length * 6.8 + 12;
          return (
            <g key={n.id}>
              {/* Card body */}
              <rect x={n.x} y={n.y} width={FGNODE_W} height={n.height}
                rx={isEnd ? n.height / 2 : 10}
                fill={colors.fill} stroke={colors.stroke} strokeWidth={1.5}
              />
              {isEnd ? (
                <text x={n.x + FGNODE_W / 2} y={n.y + n.height / 2 + 5}
                  textAnchor="middle" fontSize="14" fontWeight="700"
                  fill={colors.text} fontFamily="ui-sans-serif, system-ui, sans-serif" style={{ userSelect: 'none' }}>
                  END
                </text>
              ) : (
                <>
                  {/* Node ID */}
                  <text x={n.x + 10} y={n.y + 15} fontSize="12" fontWeight="700"
                    fill={colors.text} fontFamily="ui-sans-serif, system-ui, sans-serif" style={{ userSelect: 'none' }}>
                    {n.id.length > 22 ? n.id.slice(0, 20) + '…' : n.id}
                  </text>
                  {/* Type pill (top-right) */}
                  <rect x={n.x + FGNODE_W - tW - 8} y={n.y + 5} width={tW} height={15} rx={7.5} fill={colors.badge} />
                  <text x={n.x + FGNODE_W - tW / 2 - 8} y={n.y + 15.5} textAnchor="middle"
                    fontSize="8.5" fontWeight="600" fill={colors.text}
                    fontFamily="ui-sans-serif, system-ui, sans-serif" style={{ userSelect: 'none' }}>
                    {typeText}
                  </text>
                  {/* Separator */}
                  {n.rows.length > 0 && (
                    <line x1={n.x + 8} y1={n.y + FGNODE_HDR - 2}
                      x2={n.x + FGNODE_W - 8} y2={n.y + FGNODE_HDR - 2}
                      stroke={colors.stroke} strokeWidth={0.75} opacity={0.35}
                    />
                  )}
                  {/* Detail rows */}
                  {n.rows.map((row, ri) => {
                    const rowY = n.y + FGNODE_HDR + 4 + ri * FGNODE_ROW_H + FGNODE_ROW_H - 3;
                    const maxLen = Math.floor((FGNODE_W - 30) / 6.5);
                    const label = row.text.length > maxLen ? row.text.slice(0, maxLen - 1) + '…' : row.text;
                    return (
                      <g key={ri}>
                        {/* Left accent bar */}
                        <rect x={n.x + 8} y={n.y + FGNODE_HDR + 4 + ri * FGNODE_ROW_H + 2}
                          width={2.5} height={FGNODE_ROW_H - 4} rx={1.25} fill={row.color} opacity={0.75}
                        />
                        {/* Icon + text */}
                        <text x={n.x + 15} y={rowY} fontSize="9.5" fill="#334155"
                          fontFamily="ui-sans-serif, system-ui, sans-serif" style={{ userSelect: 'none' }}>
                          {row.icon} {label}
                        </text>
                      </g>
                    );
                  })}
                </>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
};

// ── Full-page modal wrapper (rendered via portal to escape any overflow/sticky ancestor) ──

const GraphFullPageModal: React.FC<{
  nodes: NodeConfig[];
  edges: EdgeConfig[];
  onClose: () => void;
}> = ({ nodes, edges, onClose }) => {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', h);
    // Lock body scroll while modal is open
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', h);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  const modal = (
    <div
      style={{ position: 'fixed', inset: 0, zIndex: 9999, background: 'rgba(15,23,42,0.88)', backdropFilter: 'blur(4px)', display: 'flex', flexDirection: 'column' }}
      onClick={onClose}
    >
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }} onClick={e => e.stopPropagation()}>

        {/* ── Top bar */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 24px', background: '#1e293b', borderBottom: '1px solid #334155', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <i className="fas fa-circle-nodes" style={{ color: '#818cf8', fontSize: 18 }}></i>
            <div>
              <span style={{ color: '#f1f5f9', fontWeight: 700, fontSize: 14 }}>Workflow Graph — Full Detail View</span>
              <span style={{ color: '#94a3b8', fontSize: 11, marginLeft: 12 }}>All configured settings per node · Esc to close</span>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {/* Node type legend */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {Object.entries(GNODE_COLORS).filter(([k]) => k !== 'END' && k !== 'default').map(([type, c]) => (
                <span key={type} style={{ fontSize: 9, fontWeight: 700, padding: '2px 8px', borderRadius: 99, background: c.fill, color: c.text, border: `1px solid ${c.stroke}` }}>
                  {type.replace('_', ' ')}
                </span>
              ))}
            </div>
            <button onClick={onClose}
              style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 8, border: '1px solid #475569', background: 'transparent', color: '#cbd5e1', cursor: 'pointer', fontSize: 12 }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = '#94a3b8'; (e.currentTarget as HTMLButtonElement).style.color = '#f1f5f9'; }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = '#475569'; (e.currentTarget as HTMLButtonElement).style.color = '#cbd5e1'; }}
            >
              <i className="fas fa-xmark"></i> Close
            </button>
          </div>
        </div>

        {/* ── Icon legend bar */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', padding: '6px 24px', background: 'rgba(30,41,59,0.7)', borderBottom: '1px solid rgba(51,65,85,0.5)', fontSize: 10, color: '#94a3b8', flexShrink: 0 }}>
          {[
            { icon: '🤖', text: 'LLM config' }, { icon: '⚙', text: 'tools' },
            { icon: '💾', text: 'memory' },      { icon: '⚡', text: 'pre-LLM' },
            { icon: '🔍', text: 'RAG' },          { icon: '📑', text: 'context src' },
            { icon: '📋', text: 'output schema' },{ icon: '✅', text: 'validation' },
            { icon: '🛡', text: 'out-guards' },   { icon: '🔒', text: 'in-guards' },
            { icon: '⇶', text: 'routing' },       { icon: '⏸', text: 'checkpoint' },
          ].map(b => (
            <span key={b.text} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <span>{b.icon}</span><span>{b.text}</span>
            </span>
          ))}
          <span style={{ color: '#475569', margin: '0 4px' }}>·</span>
          <span style={{ color: '#fbbf24' }}>amber dashed = conditional edge</span>
        </div>

        {/* ── Graph canvas */}
        <div style={{ flex: 1, overflow: 'auto', padding: 24, background: '#f8fafc' }}>
          {nodes.length === 0 ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#94a3b8', fontSize: 14 }}>
              No nodes defined yet. Add nodes in the builder to see the graph.
            </div>
          ) : (
            <FullPageWorkflowGraph nodes={nodes} edges={edges} />
          )}
        </div>

      </div>
    </div>
  );

  return ReactDOM.createPortal(modal, document.body);
};

// ── Right Side Panel — Graph preview + Live JSON toggle ────────────────────────

const LiveJsonSidebar: React.FC<{
  config: any;
  nodes: NodeConfig[];
  edges: EdgeConfig[];
  selectedNodeId?: string | null;
  onNodeClick?: (id: string) => void;
}> = ({ config, nodes, edges, selectedNodeId, onNodeClick }) => {
  const [view, setView] = useState<'graph' | 'json'>('graph');
  const [copied, setCopied] = useState(false);
  const [showFullPage, setShowFullPage] = useState(false);
  const text = useMemo(() => JSON.stringify(config, null, 2), [config]);

  const copy = () => {
    navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); });
  };

  return (
    <>
      {showFullPage && (
        <GraphFullPageModal nodes={nodes} edges={edges} onClose={() => setShowFullPage(false)} />
      )}
    <div className="w-64 flex-shrink-0 sticky top-4 self-start flex flex-col gap-2">
      {/* Graph / JSON toggle */}
      <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-xl">
        <button
          onClick={() => setView('graph')}
          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
            view === 'graph' ? 'bg-white shadow-sm text-indigo-700' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <i className="fas fa-circle-nodes text-[10px]"></i> Graph
        </button>
        <button
          onClick={() => setView('json')}
          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
            view === 'json' ? 'bg-white shadow-sm text-indigo-700' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <i className="fas fa-code text-[10px]"></i> JSON
        </button>
      </div>

      {/* Full-page expand — always visible when graph tab active and nodes exist */}
      {view === 'graph' && nodes.length > 0 && (
        <button
          onClick={() => setShowFullPage(true)}
          className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl border-2 border-dashed border-indigo-300 bg-indigo-50 hover:bg-indigo-100 hover:border-indigo-400 text-indigo-700 font-semibold text-xs transition-all group"
        >
          <i className="fas fa-expand-alt group-hover:scale-110 transition-transform"></i>
          Full Detail View
          <span className="text-indigo-400 font-normal text-[10px] ml-1">— all node settings</span>
        </button>
      )}

      {view === 'graph' ? (
        <div className="overflow-auto max-h-[calc(100vh-160px)]">
          {/* Legend */}
          <div className="flex flex-wrap gap-1.5 mb-2 px-1">
            {Object.entries(GNODE_COLORS).filter(([k]) => k !== 'END' && k !== 'default').map(([type, c]) => (
              <span key={type} className="flex items-center gap-1 text-[9px] font-semibold px-1.5 py-0.5 rounded-full" style={{ background: c.fill, color: c.text, border: `1px solid ${c.stroke}` }}>
                {type.replace('_', ' ')}
              </span>
            ))}
          </div>
          {/* Badge legend */}
          <div className="flex flex-wrap gap-1 mb-2 px-1">
            {([
              { label: '⚙ 2T', title: 'tools', color: '#0f766e' },
              { label: '⚡ pre', title: 'pre-LLM tools', color: '#7c3aed' },
              { label: '🔍 rag', title: 'RAG enabled', color: '#0369a1' },
              { label: '⇶ cond', title: 'conditional routing', color: '#b45309' },
              { label: '🛡 guard', title: 'guardrails', color: '#be123c' },
            ] as const).map(b => (
              <span key={b.title} title={b.title}
                className="text-[8px] font-mono px-1 py-0 rounded-full border"
                style={{ color: b.color, borderColor: b.color, background: 'white' }}>
                {b.label}
              </span>
            ))}
            <span className="text-[8px] text-slate-400 self-center ml-0.5">node badges</span>
          </div>
          <WorkflowGraphPreview
            nodes={nodes}
            edges={edges}
            selectedNodeId={selectedNodeId}
            onNodeClick={onNodeClick}
          />
          {nodes.length > 0 && (
            <p className="text-[9px] text-slate-400 text-center mt-1.5">Click a node to edit it</p>
          )}
        </div>
      ) : (
        <div className="bg-slate-900 rounded-2xl overflow-hidden shadow-lg">
          <div className="flex items-center justify-between px-3 py-2 bg-slate-800">
            <div className="flex gap-1">
              <div className="w-2.5 h-2.5 rounded-full bg-rose-500"></div>
              <div className="w-2.5 h-2.5 rounded-full bg-amber-500"></div>
              <div className="w-2.5 h-2.5 rounded-full bg-emerald-500"></div>
            </div>
            <span className="text-[10px] text-slate-400 font-mono">workflow.json</span>
            <button onClick={copy} className="text-xs text-slate-400 hover:text-white transition-colors" title="Copy JSON">
              <i className={`fas ${copied ? 'fa-check text-emerald-400' : 'fa-copy'}`}></i>
            </button>
          </div>
          <pre className="p-3 text-[10px] text-emerald-300 font-mono overflow-auto max-h-[calc(100vh-200px)] leading-relaxed whitespace-pre-wrap break-all">
            {text}
          </pre>
        </div>
      )}
    </div>
    </>
  );
};

// ── Main BuilderView ──────────────────────────────────────────────────────────

const BuilderView: React.FC<BuilderProps> = ({ initialTemplate, onNavigate }) => {
  // ── Tab state
  const [activeTab, setActiveTab] = useState('overview');

  // ── Overview
  const [graphName, setGraphName] = useState('');
  const [version, setVersion] = useState('1.0');
  const [description, setDescription] = useState('');
  const [author, setAuthor] = useState('');
  const [tags, setTags] = useState('');

  // ── State Schema
  const [stateSchema, setStateSchema] = useState<StateVar[]>([]);

  // ── Nodes
  const [nodes, setNodes] = useState<NodeConfig[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // ── Edges
  const [edges, setEdges] = useState<EdgeConfig[]>([]);

  // ── MCP Servers
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);

  // ── Runtime
  const [maxIterations, setMaxIterations] = useState(20);
  const [checkpointStore, setCheckpointStore] = useState('sqlite');
  const [tracingEnabled, setTracingEnabled] = useState(true);
  const [tracingProvider, setTracingProvider] = useState('logging');
  const [workflowTimeout, setWorkflowTimeout] = useState(300);
  const [errorPolicy, setErrorPolicy] = useState('fail_fast');
  const [maxConcurrency, setMaxConcurrency] = useState(4);

  // ── Memory
  const [stmType, setStmType] = useState('graph_state');
  const [ltmType, setLtmType] = useState('sqlite');
  const [ltmProvider, setLtmProvider] = useState('sqlite');
  const [ltmCollection, setLtmCollection] = useState('memory');
  const [stmMaxEntries, setStmMaxEntries] = useState(100);
  const [ltmTtlDays, setLtmTtlDays] = useState(90);
  const [ltmIndexFields, setLtmIndexFields] = useState('');
  const [redisUrl, setRedisUrl] = useState('');

  // ── Advanced
  const [parallelGroups, setParallelGroups] = useState<ParallelGroup[]>([]);
  const [maxRetries, setMaxRetries] = useState(3);
  const [retryIncrementState, setRetryIncrementState] = useState('retry_count');
  const [checkpointingEnabled, setCheckpointingEnabled] = useState(true);
  const [checkpointNodes, setCheckpointNodes] = useState<string[]>([]);
  const [obsTraceNodes, setObsTraceNodes] = useState(true);
  const [obsLogTransitions, setObsLogTransitions] = useState(true);
  const [obsCaptureOutputs, setObsCaptureOutputs] = useState(true);
  const [retryOn, setRetryOn] = useState<string[]>(['node_error']);
  const [backoffStrategy, setBackoffStrategy] = useState('fixed');

  // ── Run
  const [runResult, setRunResult] = useState<any>(null);
  const [runLoading, setRunLoading] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  // ── Save As Modal + versioning
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [savingTemplate, setSavingTemplate] = useState(false);
  const [templateVersions, setTemplateVersions] = useState<any[]>([]);
  const [customTemplates, setCustomTemplates] = useState<any[]>([]);
  const parentTemplateName = initialTemplate?.name ?? null;

  const { handleSave } = useWorkflowBuilder();

  // ── Load custom templates on mount
  useEffect(() => {
    getCustomTemplates().then(setCustomTemplates).catch(() => {});
  }, []);

  // ── Load versions when save modal opens
  const openSaveModal = async () => {
    if (parentTemplateName) {
      try { setTemplateVersions(await getTemplateVersions(parentTemplateName)); }
      catch { setTemplateVersions([]); }
    }
    setSaveModalOpen(true);
  };

  const handleSaveAs = async (name: string, desc: string) => {
    setSavingTemplate(true);
    try {
      await saveTemplate({
        name,
        description: desc,
        template_json: buildConfig(),
        parent_name: parentTemplateName || undefined,
        sample_prompt: '',
      });
      setNotification({ type: 'success', msg: `Saved as "${name}"` });
      // Refresh custom templates list
      getCustomTemplates().then(setCustomTemplates).catch(() => {});
      setSaveModalOpen(false);
    } catch (e: any) {
      setNotification({ type: 'error', msg: e?.response?.data?.detail || 'Save failed' });
    } finally {
      setSavingTemplate(false);
    }
  };

  // ── Auto-dismiss notification
  useEffect(() => {
    if (notification) { const t = setTimeout(() => setNotification(null), 4000); return () => clearTimeout(t); }
  }, [notification]);

  // ── Pre-fill from template
  useEffect(() => {
    if (!initialTemplate) return;
    const ex = initialTemplate.example as any;
    setGraphName(ex?.graph_name || initialTemplate.name || '');
    setVersion(ex?.version || '1.0');
    setDescription(initialTemplate.description || '');
    setAuthor(ex?.author || '');
    setTags(Array.isArray(ex?.tags) ? ex.tags.join(', ') : (ex?.tags || ''));

    if (ex?.state_schema && typeof ex.state_schema === 'object') {
      setStateSchema(Object.entries(ex.state_schema).map(([name, val]) => {
        if (typeof val === 'string') return { name, type: val as any };
        if (typeof val === 'object' && val !== null) {
          const v = val as any;
          return { name, type: v.type as any, description: v.description, default_value: v.default_value };
        }
        return { name, type: 'string' as any };
      }));
    }

    // Support both enterprise "nodes[]" format and legacy "agents[]" format
    if (Array.isArray(ex?.nodes)) {
      setNodes(ex.nodes.map((n: any) => ({
        id: n.id || '',
        type: n.type || 'agent',
        system_prompt: n.system_prompt || '',
        description: n.description || '',
        next: n.next || '',
        checkpoint: !!n.checkpoint,
        routing_logic: Array.isArray(n.routing_logic) ? n.routing_logic : [],
        tools: Array.isArray(n.tools) ? n.tools : [],
        memory_access: Array.isArray(n.memory_access) ? n.memory_access : [],
        // Per-node advanced fields
        pre_llm: n.pre_llm ?? {},
        llm_config: n.llm_config ?? {},
        context: n.context ?? {},
        output_schema: n.output_schema ?? {},
        validation: n.validation ?? {},
        guardrails: n.guardrails ?? {},
      })));
    } else if (Array.isArray(ex?.agents)) {
      // Legacy format: agents[] with "name" instead of "id"
      setNodes(ex.agents.map((a: any) => ({
        id: a.name || a.id || '',
        type: 'agent' as NodeType,
        system_prompt: a.system_prompt || '',
        description: a.description || '',
        next: a.next || 'END',
        checkpoint: false,
        routing_logic: [],
        tools: Array.isArray(a.tools) ? a.tools : [],
        memory_access: [],
        pre_llm: {},
        llm_config: {},
        context: {},
        output_schema: {},
        validation: {},
        guardrails: {},
      })));
      // Build edges from agent "next" fields
      const inferredEdges: EdgeConfig[] = (ex.agents as any[])
        .filter((a: any) => a.next && a.next !== 'END')
        .map((a: any) => ({ from: a.name || a.id || '', to: a.next, condition: '' }));
      if (inferredEdges.length > 0) setEdges(inferredEdges);
    }

    if (Array.isArray(ex?.edges)) {
      setEdges(ex.edges.map((e: any) => ({ from: e.from || '', to: e.to || '', condition: e.condition || '', label: e.label || '' })));
    }
    if (ex?.mcp_servers && typeof ex.mcp_servers === 'object') {
      setMcpServers(Object.entries(ex.mcp_servers).map(([name, cfg]: [string, any]) => ({
        name,
        type: cfg.type || 'http',
        endpoint: cfg.endpoint || '',
        command: cfg.command || '',
        args: Array.isArray(cfg.args) ? cfg.args.join(' ') : (cfg.args || ''),
        description: cfg.description || '',
        timeout_ms: cfg.timeout_ms,
        auth_header: cfg.auth_header || '',
      })));
    }
    if (ex?.runtime) {
      setMaxIterations(ex.runtime.max_iterations ?? 20);
      setCheckpointStore(ex.runtime.checkpoint_store ?? 'sqlite');
      setTracingEnabled(ex.runtime.observability?.tracing ?? true);
      setTracingProvider(ex.runtime.observability?.provider ?? 'logging');
      setWorkflowTimeout(ex.runtime.timeout_seconds ?? 300);
      setErrorPolicy(ex.runtime.error_policy ?? 'fail_fast');
      setMaxConcurrency(ex.runtime.max_concurrency ?? 4);
    }
    if (ex?.memory) {
      setStmType(ex.memory.short_term?.type ?? 'graph_state');
      setRedisUrl(ex.memory.short_term?.redis_url ?? '');
      setStmMaxEntries(ex.memory.short_term?.max_entries ?? 100);
      setLtmType(ex.memory.long_term?.type ?? 'sqlite');
      setLtmProvider(ex.memory.long_term?.provider ?? 'sqlite');
      setLtmCollection(ex.memory.long_term?.collection ?? 'memory');
      setLtmTtlDays(ex.memory.long_term?.ttl_days ?? 90);
      setLtmIndexFields(Array.isArray(ex.memory.long_term?.index_fields) ? ex.memory.long_term.index_fields.join(', ') : (ex.memory.long_term?.index_fields ?? ''));
    }
    if (Array.isArray(ex?.parallel_execution)) {
      setParallelGroups(ex.parallel_execution.map((g: any) => ({
        group: g.group || '',
        nodes: Array.isArray(g.nodes) ? g.nodes.join(', ') : '',
        timeout_ms: g.timeout_ms,
      })));
    }
    if (ex?.retry_policy) {
      setMaxRetries(ex.retry_policy.max_retries ?? 3);
      setRetryIncrementState(ex.retry_policy.increment_state ?? 'retry_count');
      setRetryOn(Array.isArray(ex.retry_policy.retry_on) ? ex.retry_policy.retry_on : ['node_error']);
      setBackoffStrategy(ex.retry_policy.backoff_strategy ?? 'fixed');
    }
    if (ex?.checkpointing) {
      setCheckpointingEnabled(ex.checkpointing.enabled ?? true);
      setCheckpointNodes(Array.isArray(ex.checkpointing.nodes) ? ex.checkpointing.nodes : []);
    }
    if (ex?.observability_hooks) {
      setObsTraceNodes(ex.observability_hooks.trace_nodes ?? true);
      setObsLogTransitions(ex.observability_hooks.log_state_transitions ?? true);
      setObsCaptureOutputs(ex.observability_hooks.capture_agent_outputs ?? true);
    }
  }, [initialTemplate]);

  // ── Build config
  const buildConfig = useCallback((): any => {
    const schema: Record<string, any> = {};
    stateSchema.forEach(v => {
      if (!v.name) return;
      if (v.description || (v.default_value !== undefined && v.default_value !== '')) {
        const obj: any = { type: v.type };
        if (v.description) obj.description = v.description;
        if (v.default_value !== undefined && v.default_value !== '') obj.default_value = v.default_value;
        schema[v.name] = obj;
      } else {
        schema[v.name] = v.type;
      }
    });

    const mcpObj: Record<string, any> = {};
    mcpServers.forEach(s => {
      if (!s.name) return;
      const cfg: any = { type: s.type };
      if (s.type === 'http' || s.type === 'sse') { if (s.endpoint) cfg.endpoint = s.endpoint; }
      if (s.type === 'stdio') {
        if (s.command) cfg.command = s.command;
        if (s.args) cfg.args = s.args.split(/\s+/).filter(Boolean);
      }
      if (s.description) cfg.description = s.description;
      if (s.timeout_ms && s.timeout_ms !== 30000) cfg.timeout_ms = s.timeout_ms;
      if (s.auth_header) cfg.auth_header = s.auth_header;
      mcpObj[s.name] = cfg;
    });

    const nodesOut = nodes.map(n => {
      const o: any = { id: n.id, type: n.type };
      if (n.system_prompt) o.system_prompt = n.system_prompt;
      if (n.description) o.description = n.description;
      if (n.checkpoint) o.checkpoint = true;
      if (n.next) o.next = n.next;
      if (n.routing_logic && n.routing_logic.length > 0) o.routing_logic = n.routing_logic;
      if (n.tools && n.tools.length > 0) o.tools = n.tools;
      if (n.memory_access && n.memory_access.length > 0) o.memory_access = n.memory_access;
      // Pre-LLM: tool calls + RAG
      const hasToolCalls = n.pre_llm?.tool_calls && n.pre_llm.tool_calls.length > 0 &&
        n.pre_llm.tool_calls.some(tc => tc.tool);
      const hasRag = n.pre_llm?.rag?.enabled;
      if (hasToolCalls || hasRag) {
        const preLlmOut: any = {};
        if (hasToolCalls) preLlmOut.tool_calls = n.pre_llm!.tool_calls!.filter(tc => tc.tool);
        if (hasRag) preLlmOut.rag = n.pre_llm!.rag;
        o.pre_llm = preLlmOut;
      }
      // Per-node advanced fields — only include if non-empty
      if (n.llm_config && Object.keys(n.llm_config).some(k => (n.llm_config as any)[k] != null))
        o.llm_config = n.llm_config;
      // Context: include if has sources OR has any input_guardrail enabled
      const hasCtxSources = n.context?.sources && n.context.sources.length > 0;
      const hasInputGuardrails = n.context?.input_guardrails &&
        Object.values(n.context.input_guardrails).some((v: any) => v?.enabled);
      if (hasCtxSources || hasInputGuardrails) {
        // Build context output, always carry synthesis if strategy is non-default
        const ctxOut: any = { ...n.context };
        if (!n.context?.synthesis?.strategy || n.context.synthesis.strategy === 'concatenate') {
          delete ctxOut.synthesis; // omit default to keep JSON clean
        }
        o.context = ctxOut;
      }
      if (n.output_schema?.format && n.output_schema.format !== 'text') o.output_schema = n.output_schema;
      else if (n.output_schema?.state_key) o.output_schema = n.output_schema;
      if (n.validation?.enabled) o.validation = n.validation;
      if (n.guardrails && Object.values(n.guardrails).some((v: any) => v?.enabled))
        o.guardrails = n.guardrails;
      return o;
    });

    const edgesOut = edges.filter(e => e.from && e.to).map(e => {
      const o: any = { from: e.from, to: e.to };
      if (e.condition) o.condition = e.condition;
      if (e.label) o.label = e.label;
      return o;
    });

    const parallelOut = parallelGroups.filter(g => g.group).map(g => {
      const o: any = { group: g.group, nodes: g.nodes.split(',').map(s => s.trim()).filter(Boolean) };
      if (g.timeout_ms) o.timeout_ms = g.timeout_ms;
      return o;
    });

    return {
      graph_name: graphName || 'my_workflow',
      version,
      ...(description ? { description } : {}),
      ...(author ? { author } : {}),
      ...(tags ? { tags: tags.split(',').map((s: string) => s.trim()).filter(Boolean) } : {}),
      runtime: {
        max_iterations: maxIterations,
        checkpoint_store: checkpointStore,
        ...(workflowTimeout !== 300 ? { timeout_seconds: workflowTimeout } : {}),
        ...(errorPolicy !== 'fail_fast' ? { error_policy: errorPolicy } : {}),
        ...(maxConcurrency !== 4 ? { max_concurrency: maxConcurrency } : {}),
        observability: { tracing: tracingEnabled, provider: tracingProvider },
      },
      memory: {
        short_term: {
          type: stmType,
          ...(stmType === 'redis' && redisUrl ? { redis_url: redisUrl } : {}),
          ...(stmMaxEntries !== 100 ? { max_entries: stmMaxEntries } : {}),
        },
        long_term: {
          type: ltmType,
          provider: ltmProvider,
          collection: ltmCollection,
          ...(ltmTtlDays !== 90 ? { ttl_days: ltmTtlDays } : {}),
          ...(ltmIndexFields ? { index_fields: ltmIndexFields.split(',').map((s: string) => s.trim()).filter(Boolean) } : {}),
        },
      },
      ...(Object.keys(mcpObj).length > 0 ? { mcp_servers: mcpObj } : {}),
      ...(Object.keys(schema).length > 0 ? { state_schema: schema } : {}),
      nodes: nodesOut,
      edges: edgesOut,
      ...(parallelOut.length > 0 ? { parallel_execution: parallelOut } : {}),
      retry_policy: {
        max_retries: maxRetries,
        increment_state: retryIncrementState,
        ...(retryOn.length > 0 && !(retryOn.length === 1 && retryOn[0] === 'node_error') ? { retry_on: retryOn } : {}),
        ...(backoffStrategy !== 'fixed' ? { backoff_strategy: backoffStrategy } : {}),
      },
      checkpointing: { enabled: checkpointingEnabled, nodes: checkpointNodes },
      observability_hooks: {
        trace_nodes: obsTraceNodes,
        log_state_transitions: obsLogTransitions,
        capture_agent_outputs: obsCaptureOutputs,
      },
    };
  }, [
    graphName, version, description, author, tags, stateSchema, nodes, edges, mcpServers,
    maxIterations, checkpointStore, tracingEnabled, tracingProvider,
    workflowTimeout, errorPolicy, maxConcurrency,
    stmType, ltmType, ltmProvider, ltmCollection,
    stmMaxEntries, ltmTtlDays, ltmIndexFields, redisUrl,
    parallelGroups, maxRetries, retryIncrementState, retryOn, backoffStrategy,
    checkpointingEnabled, checkpointNodes,
    obsTraceNodes, obsLogTransitions, obsCaptureOutputs,
  ]);

  const config = useMemo(() => buildConfig(), [buildConfig]);
  const nodeIds = useMemo(() => nodes.map(n => n.id).filter(Boolean), [nodes]);
  const stateKeys = useMemo(() => stateSchema.map(v => v.name).filter(Boolean), [stateSchema]);
  const selectedNode = useMemo(() => nodes.find(n => n.id === selectedNodeId) ?? null, [nodes, selectedNodeId]);

  const updateSelectedNode = (updated: NodeConfig) => {
    setNodes(prev => prev.map(n => n.id === selectedNodeId ? updated : n));
    setSelectedNodeId(updated.id);
  };

  const addNode = () => {
    const id = `Node${nodes.length + 1}`;
    setNodes(prev => [...prev, { id, type: 'agent', system_prompt: '', next: 'END', routing_logic: [], tools: [], memory_access: [] }]);
    setSelectedNodeId(id);
  };

  const removeNode = (id: string) => {
    setNodes(prev => prev.filter(n => n.id !== id));
    if (selectedNodeId === id) setSelectedNodeId(nodes.find(n => n.id !== id)?.id ?? null);
  };

  // ── Tab Panels ───────────────────────────────────────────────────────────────

  const renderOverview = () => (
    <div className="space-y-6 max-w-xl">
      <HelpPanel {...HELP.overview} />
      <SectionTitle icon="fa-layer-group">Workflow Overview</SectionTitle>
      {initialTemplate && (
        <div className="flex items-center gap-3 p-4 bg-indigo-50 border border-indigo-200 rounded-xl">
          <i className="fas fa-file-code text-indigo-500"></i>
          <div>
            <p className="text-xs text-indigo-500 font-semibold uppercase tracking-wider">Template loaded</p>
            <p className="text-sm font-bold text-indigo-800">{initialTemplate.name}</p>
          </div>
        </div>
      )}
      <div>
        <FieldLabel hint="Unique name for this workflow graph. Use underscores, no spaces.">Graph Name</FieldLabel>
        <Input value={graphName} onChange={e => setGraphName(e.target.value)} placeholder="e.g. Enterprise_Agent_Workflow" />
      </div>
      <div>
        <FieldLabel hint="Semantic version of this workflow config.">Version</FieldLabel>
        <Input value={version} onChange={e => setVersion(e.target.value)} placeholder="1.0" className="w-32" />
      </div>
      <div>
        <FieldLabel hint="Human-readable description of what this workflow does.">Description</FieldLabel>
        <Textarea rows={3} value={description} onChange={e => setDescription(e.target.value)} placeholder="Describe what this workflow does..." />
      </div>
      <div>
        <FieldLabel hint="Author or team responsible for this workflow.">Author</FieldLabel>
        <Input value={author} onChange={e => setAuthor(e.target.value)} placeholder="e.g. Data Science Team" />
      </div>
      <div>
        <FieldLabel hint="Comma-separated tags for categorization and search.">Tags</FieldLabel>
        <Input value={tags} onChange={e => setTags(e.target.value)} placeholder="e.g. research, production, nlp" />
        {tags && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {tags.split(',').map(t => t.trim()).filter(Boolean).map((tag, i) => (
              <span key={i} className="px-2 py-0.5 bg-indigo-100 text-indigo-700 text-xs font-medium rounded-full">{tag}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  );

  const renderStateSchema = () => (
    <div className="space-y-4 max-w-2xl">
      <HelpPanel {...HELP.schema} />
      <div className="flex items-center justify-between">
        <SectionTitle icon="fa-table-columns">State Schema Variables</SectionTitle>
        <button onClick={() => setStateSchema(prev => [...prev, { name: '', type: 'string' }])}
          className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors font-semibold">
          + Add Variable
        </button>
      </div>
      <p className="text-xs text-slate-400">Define the shared state variables that agents read and write during the workflow.</p>
      {stateSchema.length === 0 && (
        <div className="py-10 text-center border-2 border-dashed border-slate-200 rounded-xl text-slate-400 text-sm">
          No state variables yet. Add one above.
        </div>
      )}
      <div className="space-y-2">
        {stateSchema.map((v, i) => (
          <div key={i} className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
            <div className="flex gap-3 items-center">
              <Input value={v.name} onChange={e => setStateSchema(prev => prev.map((x, idx) => idx === i ? { ...x, name: e.target.value } : x))}
                placeholder="variable_name" className="flex-1" />
              <Select value={v.type} onChange={e => setStateSchema(prev => prev.map((x, idx) => idx === i ? { ...x, type: e.target.value as any } : x))}
                className="w-36">
                <option value="string">string</option>
                <option value="integer">integer</option>
                <option value="float">float</option>
                <option value="boolean">boolean</option>
                <option value="list">list</option>
                <option value="dict">dict</option>
              </Select>
              <button onClick={() => setStateSchema(prev => prev.filter((_, idx) => idx !== i))}
                className="text-slate-300 hover:text-rose-500 transition-colors px-2">
                <i className="fas fa-trash-alt text-sm"></i>
              </button>
            </div>
            <div className="flex gap-2">
              <Input value={v.description ?? ''} onChange={e => setStateSchema(prev => prev.map((x, idx) => idx === i ? { ...x, description: e.target.value } : x))}
                placeholder="description (optional)" className="flex-1 text-xs" />
              <Input value={v.default_value ?? ''} onChange={e => setStateSchema(prev => prev.map((x, idx) => idx === i ? { ...x, default_value: e.target.value } : x))}
                placeholder="default value" className="w-32 text-xs font-mono" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  const renderNodes = () => (
    <div className="flex gap-6 h-full">
      {/* Node list */}
      <div className="w-56 flex-shrink-0 space-y-2">
        <div className="mb-3">
          <div className="p-3 bg-indigo-50 border border-indigo-100 rounded-xl mb-2">
            <p className="text-[10px] font-bold text-indigo-500 uppercase tracking-widest mb-1">Node Types</p>
            {[['fa-robot','agent','LLM agent'],['fa-wrench','tool_node','Runs tools'],['fa-code-branch','conditional','Routing only'],['fa-user-check','human_node','Pause for human']].map(([ico,t,d]) => (
              <div key={t} className="flex items-center gap-1.5 py-0.5">
                <i className={`fas ${ico} text-indigo-400 text-[10px] w-3`}></i>
                <span className="text-[10px] text-slate-600 font-medium">{t}</span>
                <span className="text-[10px] text-slate-400">— {d}</span>
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-widest">{nodes.length} Nodes</span>
            <button onClick={addNode} className="text-xs px-2 py-1 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">+ Add</button>
          </div>
        </div>
        {nodes.length === 0 && (
          <div className="py-8 text-center border-2 border-dashed border-slate-200 rounded-xl text-slate-400 text-xs">
            No nodes yet
          </div>
        )}
        {nodes.map(n => (
          <div key={n.id}
            onClick={() => setSelectedNodeId(n.id)}
            className={`flex items-center gap-2 p-2.5 rounded-xl border cursor-pointer transition-all ${selectedNodeId === n.id ? 'border-indigo-400 bg-indigo-50' : 'border-slate-200 bg-white hover:bg-slate-50'}`}>
            <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${NODE_BADGES[n.type as NodeType] ?? 'bg-slate-100 text-slate-500'}`}>
              <i className={`fas ${NODE_ICONS[n.type as NodeType] ?? 'fa-circle'} text-xs`}></i>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-bold text-slate-800 truncate">{n.id || <em className="text-slate-400">unnamed</em>}</p>
              <p className="text-[10px] text-slate-400">{n.type}</p>
            </div>
            <button onClick={e => { e.stopPropagation(); removeNode(n.id); }}
              className="text-slate-300 hover:text-rose-500 transition-colors">
              <i className="fas fa-xmark text-xs"></i>
            </button>
          </div>
        ))}
      </div>

      {/* Node detail */}
      <div className="flex-1 bg-white border border-slate-200 rounded-2xl p-6 overflow-auto">
        {selectedNode ? (
          <>
            <div className="flex items-center gap-2 mb-5">
              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${NODE_BADGES[selectedNode.type]}`}>{selectedNode.type}</span>
              <span className="text-sm font-bold text-slate-700">{selectedNode.id}</span>
            </div>
            <NodeDetailPanel node={selectedNode} onChange={updateSelectedNode} stateKeys={stateKeys} stateVars={stateSchema} />
          </>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center py-16 text-slate-400">
            <i className="fas fa-circle-nodes text-4xl mb-3 text-slate-200"></i>
            <p className="text-sm font-medium">Select a node to edit</p>
            <p className="text-xs mt-1">or click "+ Add" to create one</p>
          </div>
        )}
      </div>
    </div>
  );

  const renderEdges = () => (
    <div className="space-y-4 max-w-3xl">
      <HelpPanel {...HELP.edges} />
      <div className="flex items-center justify-between">
        <SectionTitle icon="fa-bezier-curve">Edges</SectionTitle>
        <button onClick={() => setEdges(prev => [...prev, { from: '', to: '', condition: '' }])}
          className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors font-semibold">
          + Add Edge
        </button>
      </div>
      <p className="text-xs text-slate-400">Explicit edges connect nodes. Conditional edges fire only when the condition is met. Leave condition blank for unconditional edges.</p>
      {edges.length === 0 && (
        <div className="py-10 text-center border-2 border-dashed border-slate-200 rounded-xl text-slate-400 text-sm">
          No edges defined. Nodes can also use their "next" field for simple routing.
        </div>
      )}
      <div className="space-y-2">
        {edges.map((e, i) => (
          <div key={i} className="flex gap-3 items-center p-3 bg-slate-50 rounded-xl border border-slate-200">
            <Select value={e.from} onChange={ev => setEdges(prev => prev.map((x, idx) => idx === i ? { ...x, from: ev.target.value } : x))} className="w-36 flex-shrink-0">
              <option value="">from…</option>
              {nodeIds.map(id => <option key={id} value={id}>{id}</option>)}
            </Select>
            <i className="fas fa-arrow-right text-slate-400 flex-shrink-0"></i>
            <Select value={e.to} onChange={ev => setEdges(prev => prev.map((x, idx) => idx === i ? { ...x, to: ev.target.value } : x))} className="w-36 flex-shrink-0">
              <option value="">to…</option>
              {[...nodeIds, 'END'].map(id => <option key={id} value={id}>{id}</option>)}
            </Select>
            <ConditionBuilder
              value={e.condition ?? ''}
              onChange={v => setEdges(prev => prev.map((x, idx) => idx === i ? { ...x, condition: v } : x))}
              stateVars={stateSchema}
              placeholder="condition (optional — leave blank for unconditional)"
            />
            <Input value={e.label ?? ''} onChange={ev => setEdges(prev => prev.map((x, idx) => idx === i ? { ...x, label: ev.target.value } : x))}
              placeholder="label (opt)" className="w-28 flex-shrink-0 text-xs" />
            <button onClick={() => setEdges(prev => prev.filter((_, idx) => idx !== i))}
              className="text-slate-300 hover:text-rose-500 transition-colors flex-shrink-0">
              <i className="fas fa-trash-alt text-sm"></i>
            </button>
          </div>
        ))}
      </div>
    </div>
  );

  const renderMCP = () => (
    <div className="space-y-4 max-w-2xl">
      <HelpPanel {...HELP.mcp} />
      <div className="flex items-center justify-between">
        <SectionTitle icon="fa-plug">MCP Servers</SectionTitle>
        <button onClick={() => setMcpServers(prev => [...prev, { name: '', type: 'http', endpoint: '' }])}
          className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors font-semibold">
          + Add Server
        </button>
      </div>
      <p className="text-xs text-slate-400">Define MCP (Model Context Protocol) tool servers. Tools from these servers are auto-discovered and bound to agents.</p>
      {mcpServers.length === 0 && (
        <div className="py-10 text-center border-2 border-dashed border-slate-200 rounded-xl text-slate-400 text-sm">
          No MCP servers configured.
        </div>
      )}
      <div className="space-y-4">
        {mcpServers.map((s, i) => (
          <div key={i} className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
            <div className="flex gap-3 items-center">
              <Input value={s.name} onChange={e => setMcpServers(prev => prev.map((x, idx) => idx === i ? { ...x, name: e.target.value } : x))}
                placeholder="Server name (e.g. web_search)" className="flex-1" />
              <Select value={s.type} onChange={e => setMcpServers(prev => prev.map((x, idx) => idx === i ? { ...x, type: e.target.value as any } : x))}
                className="w-28">
                <option value="http">http</option>
                <option value="stdio">stdio</option>
                <option value="sse">sse</option>
              </Select>
              <button onClick={() => setMcpServers(prev => prev.filter((_, idx) => idx !== i))}
                className="text-slate-300 hover:text-rose-500 transition-colors">
                <i className="fas fa-trash-alt"></i>
              </button>
            </div>
            {(s.type === 'http' || s.type === 'sse') && (
              <div>
                <FieldLabel hint="HTTP/SSE endpoint URL for this MCP server">Endpoint URL</FieldLabel>
                <Input value={s.endpoint ?? ''} onChange={e => setMcpServers(prev => prev.map((x, idx) => idx === i ? { ...x, endpoint: e.target.value } : x))}
                  placeholder="https://api.example.com/mcp" />
              </div>
            )}
            {s.type === 'stdio' && (
              <div className="space-y-2">
                <div>
                  <FieldLabel hint="Command to launch the stdio MCP server process">Command</FieldLabel>
                  <Input value={s.command ?? ''} onChange={e => setMcpServers(prev => prev.map((x, idx) => idx === i ? { ...x, command: e.target.value } : x))}
                    placeholder="e.g. python" />
                </div>
                <div>
                  <FieldLabel hint="Space-separated arguments for the command">Args</FieldLabel>
                  <Input value={s.args ?? ''} onChange={e => setMcpServers(prev => prev.map((x, idx) => idx === i ? { ...x, args: e.target.value } : x))}
                    placeholder="e.g. -m my_mcp_server" />
                </div>
              </div>
            )}
            <div className="grid grid-cols-3 gap-2 pt-1">
              <div>
                <FieldLabel hint="Human-readable description of this MCP server">Description</FieldLabel>
                <Input value={s.description ?? ''} onChange={e => setMcpServers(prev => prev.map((x, idx) => idx === i ? { ...x, description: e.target.value } : x))}
                  placeholder="optional description" className="text-xs" />
              </div>
              <div>
                <FieldLabel hint="Request timeout in milliseconds (default 30000)">Timeout (ms)</FieldLabel>
                <Input type="number" value={s.timeout_ms ?? 30000} onChange={e => setMcpServers(prev => prev.map((x, idx) => idx === i ? { ...x, timeout_ms: Number(e.target.value) || undefined } : x))}
                  placeholder="30000" className="text-xs" />
              </div>
              <div>
                <FieldLabel hint="Authorization header value (e.g. Bearer sk-...)">Auth Header</FieldLabel>
                <Input value={s.auth_header ?? ''} onChange={e => setMcpServers(prev => prev.map((x, idx) => idx === i ? { ...x, auth_header: e.target.value } : x))}
                  placeholder="Bearer sk-..." className="text-xs" />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  const renderRuntime = () => (
    <div className="space-y-8 max-w-2xl">
      <HelpPanel {...HELP.runtime} />
      {/* Runtime section */}
      <div>
        <SectionTitle icon="fa-microchip">Runtime Settings</SectionTitle>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <FieldLabel hint="Maximum number of graph execution iterations before stopping">Max Iterations</FieldLabel>
              <Input type="number" value={maxIterations} onChange={e => setMaxIterations(Number(e.target.value))} min={1} max={1000} />
            </div>
            <div>
              <FieldLabel hint="Backend used to persist checkpoints between steps">Checkpoint Store</FieldLabel>
              <Select value={checkpointStore} onChange={e => setCheckpointStore(e.target.value)}>
                <option value="sqlite">sqlite</option>
                <option value="postgres">postgres</option>
                <option value="memory">memory</option>
              </Select>
            </div>
            <div>
              <FieldLabel hint="Overall workflow timeout in seconds (default 300). Requires asyncio enforcement.">Workflow Timeout (s)</FieldLabel>
              <Input type="number" value={workflowTimeout} onChange={e => setWorkflowTimeout(Number(e.target.value))} min={1} max={86400} />
            </div>
            <div>
              <FieldLabel hint="Error handling policy: fail_fast halts on first error; continue logs and proceeds.">Error Policy</FieldLabel>
              <Select value={errorPolicy} onChange={e => setErrorPolicy(e.target.value)}>
                <option value="fail_fast">fail_fast (halt on error)</option>
                <option value="continue">continue (log and proceed)</option>
                <option value="retry">retry (use retry_policy)</option>
              </Select>
            </div>
            <div>
              <FieldLabel hint="Maximum concurrent node executions (default 4). Requires LangGraph thread config.">Max Concurrency</FieldLabel>
              <Input type="number" value={maxConcurrency} onChange={e => setMaxConcurrency(Number(e.target.value))} min={1} max={64} />
            </div>
          </div>
          <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
            <p className="text-xs font-bold text-slate-500 uppercase tracking-widest">Observability</p>
            <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
              <input type="checkbox" checked={tracingEnabled} onChange={e => setTracingEnabled(e.target.checked)} className="w-4 h-4 rounded" />
              Enable tracing
            </label>
            <div>
              <FieldLabel hint="Observability backend provider">Provider</FieldLabel>
              <Select value={tracingProvider} onChange={e => setTracingProvider(e.target.value)} className="w-48">
                <option value="logging">logging</option>
                <option value="langsmith">langsmith</option>
                <option value="otel">otel (OpenTelemetry)</option>
              </Select>
            </div>
          </div>
        </div>
      </div>

      <Divider />

      {/* Memory section */}
      <div>
        <SectionTitle icon="fa-brain">Memory Configuration</SectionTitle>
        <div className="space-y-4">
          <div>
            <FieldLabel hint="Short-term memory (STM) holds state within a single run">Short-Term Memory Type</FieldLabel>
            <Select value={stmType} onChange={e => setStmType(e.target.value)} className="w-48">
              <option value="graph_state">graph_state (default)</option>
              <option value="redis">redis</option>
            </Select>
          </div>
          {stmType === 'redis' && (
            <div>
              <FieldLabel hint="Redis connection URL for short-term memory storage">Redis URL</FieldLabel>
              <Input value={redisUrl} onChange={e => setRedisUrl(e.target.value)} placeholder="redis://localhost:6379/0" />
            </div>
          )}
          <div>
            <FieldLabel hint="Maximum number of STM entries to retain per session (default 100)">Max STM Entries</FieldLabel>
            <Input type="number" value={stmMaxEntries} onChange={e => setStmMaxEntries(Number(e.target.value))} min={1} max={10000} className="w-32" />
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <FieldLabel hint="Long-term memory persists across runs">LTM Type</FieldLabel>
              <Select value={ltmType} onChange={e => setLtmType(e.target.value)}>
                <option value="sqlite">sqlite</option>
                <option value="vector_db">vector_db</option>
                <option value="none">none</option>
              </Select>
            </div>
            <div>
              <FieldLabel hint="Storage provider for long-term memory">LTM Provider</FieldLabel>
              <Input value={ltmProvider} onChange={e => setLtmProvider(e.target.value)} placeholder="sqlite" />
            </div>
            <div>
              <FieldLabel hint="Collection / table name for long-term memory">Collection</FieldLabel>
              <Input value={ltmCollection} onChange={e => setLtmCollection(e.target.value)} placeholder="memory" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <FieldLabel hint="Days to retain LTM entries before expiry (default 90). Set 0 for no expiry.">LTM TTL (days)</FieldLabel>
              <Input type="number" value={ltmTtlDays} onChange={e => setLtmTtlDays(Number(e.target.value))} min={0} max={3650} />
            </div>
            <div>
              <FieldLabel hint="Comma-separated LTM field names to index for faster search (e.g. session_id, task)">LTM Index Fields</FieldLabel>
              <Input value={ltmIndexFields} onChange={e => setLtmIndexFields(e.target.value)} placeholder="e.g. session_id, task" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const renderAdvanced = () => (
    <div className="space-y-8 max-w-2xl">
      <HelpPanel {...HELP.advanced} />
      {/* Parallel groups */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <SectionTitle icon="fa-arrows-split-up-and-left">Parallel Execution Groups</SectionTitle>
          <button onClick={() => setParallelGroups(prev => [...prev, { group: '', nodes: '' }])}
            className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors font-semibold">
            + Add Group
          </button>
        </div>
        <p className="text-xs text-slate-400 mb-3">Nodes in a group run in parallel. Enter comma-separated node IDs.</p>
        {parallelGroups.map((g, i) => (
          <div key={i} className="flex gap-3 items-center mb-2">
            <Input value={g.group} onChange={e => setParallelGroups(prev => prev.map((x, idx) => idx === i ? { ...x, group: e.target.value } : x))}
              placeholder="group name" className="w-40" />
            <Input value={g.nodes} onChange={e => setParallelGroups(prev => prev.map((x, idx) => idx === i ? { ...x, nodes: e.target.value } : x))}
              placeholder="NodeA, NodeB, NodeC" className="flex-1" />
            <Input type="number" value={g.timeout_ms ?? ''} onChange={e => setParallelGroups(prev => prev.map((x, idx) => idx === i ? { ...x, timeout_ms: Number(e.target.value) || undefined } : x))}
              placeholder="timeout ms" className="w-28" />
            <button onClick={() => setParallelGroups(prev => prev.filter((_, idx) => idx !== i))}
              className="text-slate-300 hover:text-rose-500 transition-colors">
              <i className="fas fa-trash-alt"></i>
            </button>
          </div>
        ))}
        {parallelGroups.length === 0 && (
          <p className="text-xs text-slate-400 italic">No parallel groups defined.</p>
        )}
      </div>

      <Divider />

      {/* Retry policy */}
      <div>
        <SectionTitle icon="fa-rotate-right">Retry Policy</SectionTitle>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <FieldLabel hint="Maximum number of retries on node failure">Max Retries</FieldLabel>
            <Input type="number" value={maxRetries} onChange={e => setMaxRetries(Number(e.target.value))} min={0} max={20} />
          </div>
          <div>
            <FieldLabel hint="State variable to increment on each retry">Increment State Variable</FieldLabel>
            <Select value={retryIncrementState} onChange={e => setRetryIncrementState(e.target.value)}>
              {stateKeys.length === 0 && <option value="">— define state vars first —</option>}
              {stateKeys.map(k => <option key={k} value={k}>{k}</option>)}
              <option value="retry_count">retry_count (custom)</option>
            </Select>
          </div>
        </div>
          <div className="space-y-2">
            <FieldLabel hint="Which error types should trigger a retry">Retry On (error types)</FieldLabel>
            <div className="flex flex-wrap gap-3">
              {(['node_error', 'guardrail_block', 'validation_fail', 'timeout'] as const).map(et => (
                <label key={et} className="flex items-center gap-1.5 text-xs text-slate-700 cursor-pointer">
                  <input type="checkbox" checked={retryOn.includes(et)}
                    onChange={e => setRetryOn(prev => e.target.checked ? [...prev, et] : prev.filter(x => x !== et))}
                    className="w-3.5 h-3.5 rounded" />
                  {et}
                </label>
              ))}
            </div>
          </div>
          <div>
            <FieldLabel hint="Backoff strategy between retries">Backoff Strategy</FieldLabel>
            <Select value={backoffStrategy} onChange={e => setBackoffStrategy(e.target.value)} className="w-48">
              <option value="fixed">fixed (constant delay)</option>
              <option value="exponential">exponential (doubling delay)</option>
            </Select>
          </div>
      </div>

      <Divider />

      {/* Checkpointing */}
      <div>
        <SectionTitle icon="fa-floppy-disk">Checkpointing</SectionTitle>
        <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer mb-4">
          <input type="checkbox" checked={checkpointingEnabled} onChange={e => setCheckpointingEnabled(e.target.checked)} className="w-4 h-4 rounded" />
          Enable checkpointing
        </label>
        {checkpointingEnabled && (
          <div>
            <FieldLabel hint="Select which nodes should create checkpoints">Checkpoint Nodes</FieldLabel>
            <div className="flex flex-wrap gap-2 mt-1">
              {nodeIds.length === 0 && <p className="text-xs text-slate-400 italic">Add nodes first.</p>}
              {nodeIds.map(id => (
                <label key={id} className="flex items-center gap-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 cursor-pointer hover:bg-slate-100 transition-colors">
                  <input type="checkbox" checked={checkpointNodes.includes(id)}
                    onChange={e => setCheckpointNodes(prev => e.target.checked ? [...prev, id] : prev.filter(n => n !== id))}
                    className="w-3 h-3 rounded" />
                  {id}
                </label>
              ))}
            </div>
          </div>
        )}
      </div>

      <Divider />

      {/* Observability hooks */}
      <div>
        <SectionTitle icon="fa-eye">Observability Hooks</SectionTitle>
        <div className="space-y-2">
          {([
            ['obsTraceNodes', 'Trace node executions', obsTraceNodes, setObsTraceNodes],
            ['obsLogTransitions', 'Log state transitions', obsLogTransitions, setObsLogTransitions],
            ['obsCaptureOutputs', 'Capture agent outputs', obsCaptureOutputs, setObsCaptureOutputs],
          ] as const).map(([, label, val, setter]) => (
            <label key={label} className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
              <input type="checkbox" checked={val} onChange={e => (setter as any)(e.target.checked)} className="w-4 h-4 rounded" />
              {label}
            </label>
          ))}
        </div>
      </div>
    </div>
  );

  // ── Flow diagram (simple ASCII)
  const buildFlowDiagram = () => {
    if (nodes.length === 0) return 'No nodes defined.';
    const lines: string[] = [];
    const drawn = new Set<string>();
    const render = (id: string, depth: number) => {
      if (drawn.has(id) || depth > 10) return;
      drawn.add(id);
      const node = nodes.find(n => n.id === id);
      const pad = '  '.repeat(depth);
      lines.push(`${pad}[${id}${node ? ' (' + node.type + ')' : ''}]`);
      if (node?.next && node.next !== 'END') render(node.next, depth + 1);
      if (node?.routing_logic) {
        node.routing_logic.forEach(r => { if (r.next) { lines.push(`${pad}  ↳ ${r.condition} → ${r.next}`); render(r.next, depth + 1); } });
      }
    };
    if (nodes.length > 0) render(nodes[0].id, 0);
    nodes.forEach(n => { if (!drawn.has(n.id)) render(n.id, 0); });
    return lines.join('\n');
  };

  const renderRun = () => {
    const cfg = config;
    const statusColor = runResult?.status === 'completed' ? 'emerald' : runResult?.status === 'error' ? 'rose' : 'indigo';

    const handleRun = async () => {
      setRunLoading(true); setRunError(null); setRunResult(null); setRunId(null);
      try {
        const res = await orchestrateAsync(cfg as any);
        setRunId(res.run_id);
        setNotification({ type: 'success', msg: `Workflow started — run ID: ${res.run_id}` });
        // poll
        let polls = 0;
        const poll = async (id: string) => {
          if (polls++ > 60) return;
          const s = await getStatus(id);
          setRunResult(s);
          if (s.status !== 'completed' && s.status !== 'error') setTimeout(() => poll(id), 2500);
          else setRunLoading(false);
        };
        poll(res.run_id);
      } catch (e: any) {
        setRunError(e?.response?.data?.detail || e?.message || 'Orchestration failed');
        setRunLoading(false);
      }
    };

    const handleSaveTemplate = async () => {
      await openSaveModal();
    };

    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left: summary */}
        <div className="space-y-6">
          <HelpPanel {...HELP.run} />
          <div className="p-5 bg-white border border-slate-200 rounded-2xl space-y-4">
            <SectionTitle icon="fa-clipboard-list">Workflow Summary</SectionTitle>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-slate-500">Name</span><span className="font-mono font-bold text-slate-800">{cfg.graph_name}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Version</span><span className="font-bold text-slate-800">{cfg.version}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Nodes</span><span className="font-bold text-slate-800">{cfg.nodes?.length ?? 0}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Edges</span><span className="font-bold text-slate-800">{cfg.edges?.length ?? 0}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">State variables</span><span className="font-bold text-slate-800">{Object.keys(cfg.state_schema ?? {}).length}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">MCP servers</span><span className="font-bold text-slate-800">{Object.keys(cfg.mcp_servers ?? {}).length}</span></div>
            </div>
          </div>

          {/* ASCII flow diagram — textual connectivity summary */}
          <div className="p-5 bg-slate-900 rounded-2xl">
            <p className="text-xs text-slate-400 font-bold uppercase tracking-widest mb-3">
              <i className="fas fa-diagram-project mr-1.5 text-slate-500"></i>Connectivity Summary
            </p>
            <pre className="text-xs text-emerald-300 font-mono leading-relaxed whitespace-pre-wrap">
              {buildFlowDiagram()}
            </pre>
          </div>

          {/* Actions */}
          <div className="space-y-3">
            <button onClick={handleSaveTemplate}
              className="w-full py-3 bg-white border-2 border-slate-200 hover:border-indigo-300 hover:bg-indigo-50 text-slate-700 hover:text-indigo-700 font-semibold rounded-xl flex items-center justify-center gap-2 transition-all">
              <i className="fas fa-save"></i> Save as Template…
            </button>
            <button onClick={handleRun} disabled={runLoading}
              className="w-full py-3.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold rounded-xl flex items-center justify-center gap-2 transition-colors shadow-lg shadow-indigo-200">
              {runLoading
                ? <><i className="fas fa-spinner fa-spin"></i> Running...</>
                : <><i className="fas fa-play"></i> Run Workflow</>}
            </button>
          </div>

          {/* My Saved Templates (custom versions) */}
          {customTemplates.length > 0 && (
            <div className="p-4 bg-white border border-slate-200 rounded-2xl">
              <SectionTitle icon="fa-bookmark">My Saved Templates</SectionTitle>
              <div className="space-y-2 max-h-52 overflow-auto">
                {customTemplates.map((t, i) => (
                  <div key={i} className="flex items-center justify-between px-3 py-2.5 bg-slate-50 rounded-xl border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50 transition-all group cursor-pointer"
                    onClick={() => onNavigate?.('/builder', { template: t })}>
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="flex-shrink-0 w-6 h-6 bg-indigo-100 text-indigo-600 rounded-lg flex items-center justify-center text-[10px] font-bold">v{t.version ?? 1}</span>
                      <div className="min-w-0">
                        <p className="text-xs font-bold text-slate-700 group-hover:text-indigo-700 truncate">{t.name}</p>
                        {t.parent_name && <p className="text-[10px] text-slate-400 truncate">from: {t.parent_name}</p>}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {t.updated_at && (
                        <span className="text-[10px] text-slate-400">{new Date(t.updated_at).toLocaleDateString()}</span>
                      )}
                      <i className="fas fa-chevron-right text-slate-300 text-xs group-hover:text-indigo-400 transition-colors"></i>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right: result */}
        <div>
          {runError && (
            <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-sm mb-4">
              <i className="fas fa-circle-exclamation mr-2"></i>{runError}
            </div>
          )}
          {!runId && !runError ? (
            <div className="flex flex-col items-center justify-center py-20 text-center bg-white border border-slate-200 rounded-2xl">
              <i className="fas fa-play-circle text-slate-200 text-5xl mb-4"></i>
              <p className="text-slate-500 font-medium">Ready to run</p>
              <p className="text-xs text-slate-400 mt-1">Click "Run Workflow" to execute</p>
            </div>
          ) : runId && (
            <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
              <div className={`px-5 py-4 border-b border-slate-100 bg-${statusColor}-50 flex items-center justify-between`}>
                <div>
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-0.5">Run ID</p>
                  <p className="font-mono text-sm font-bold text-slate-800">{runId}</p>
                </div>
                <span className={`px-3 py-1 rounded-full text-xs font-bold bg-${statusColor}-100 text-${statusColor}-700`}>
                  {runResult?.status ?? (runLoading ? 'running…' : 'started')}
                </span>
              </div>
              {runResult?.result && (
                <div className="p-5">
                  <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Result</p>
                  <pre className="text-xs text-slate-700 bg-slate-50 rounded-xl p-3 overflow-auto max-h-64 font-mono whitespace-pre-wrap">
                    {typeof runResult.result === 'string' ? runResult.result : JSON.stringify(runResult.result, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    );
  };

  const tabContent: Record<string, () => React.ReactNode> = {
    overview: renderOverview,
    schema: renderStateSchema,
    nodes: renderNodes,
    edges: renderEdges,
    mcp: renderMCP,
    runtime: renderRuntime,
    advanced: renderAdvanced,
    run: renderRun,
  };

  return (
    <div className="flex h-full min-h-screen bg-slate-50">
      {/* ── Left vertical tab bar */}
      <div className="w-44 flex-shrink-0 bg-white border-r border-slate-200 flex flex-col py-6 px-3 gap-1">
        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest px-2 mb-3">Workflow Builder</p>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium transition-all text-left w-full ${
              activeTab === tab.id
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            }`}
          >
            <i className={`fas ${tab.icon} w-4 text-center text-xs flex-shrink-0 ${activeTab === tab.id ? 'text-white' : 'text-slate-400'}`}></i>
            <span className="truncate">{tab.label}</span>
            {tab.id === 'run' && (
              <span className={`ml-auto text-[10px] font-bold px-1.5 py-0.5 rounded-full ${activeTab === tab.id ? 'bg-white/20 text-white' : 'bg-emerald-100 text-emerald-600'}`}>GO</span>
            )}
          </button>
        ))}
      </div>

      {/* ── Center: tab content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Notification */}
        {notification && (
          <div className={`mx-6 mt-4 flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium ${
            notification.type === 'success' ? 'bg-emerald-50 border border-emerald-200 text-emerald-700' : 'bg-rose-50 border border-rose-200 text-rose-700'
          }`}>
            <i className={`fas ${notification.type === 'success' ? 'fa-circle-check' : 'fa-circle-exclamation'}`}></i>
            {notification.msg}
            <button onClick={() => setNotification(null)} className="ml-auto opacity-50 hover:opacity-100">
              <i className="fas fa-xmark"></i>
            </button>
          </div>
        )}

        <div className="flex flex-1 overflow-hidden gap-0">
          {/* Tab panel */}
          <div className="flex-1 overflow-auto p-6">
            {tabContent[activeTab]?.()}
          </div>

          {/* ── Right: live graph + JSON panel */}
          <div className="p-4 border-l border-slate-200 bg-white">
            <LiveJsonSidebar
              config={config}
              nodes={nodes}
              edges={edges}
              selectedNodeId={selectedNodeId}
              onNodeClick={(id) => { setSelectedNodeId(id); setActiveTab('nodes'); }}
            />
          </div>
        </div>
      </div>

      {/* ── Save As Modal */}
      {saveModalOpen && (
        <SaveAsModal
          open={saveModalOpen}
          initialName={graphName}
          initialDescription={description}
          parentName={parentTemplateName ?? undefined}
          versions={templateVersions}
          saving={savingTemplate}
          onSave={handleSaveAs}
          onClose={() => setSaveModalOpen(false)}
        />
      )}
    </div>
  );
};

export default BuilderView;
