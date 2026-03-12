import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { TemplateInfo } from '../types';
import { useWorkflowBuilder } from '../hooks/useWorkflowBuilder';
import { saveTemplate, orchestrateAsync, getStatus } from '../services/api';

// ── Local Types ──────────────────────────────────────────────────────────────

interface BuilderProps {
  initialTemplate?: { name?: string; description?: string; sample_prompt?: string; example?: any; source_file?: string; } | null;
  onNavigate?: (path: string, data?: any) => void;
}

type NodeType = 'agent' | 'tool_node' | 'conditional' | 'human_node';

interface RoutingRule {
  condition: string;
  next: string;
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
}

interface EdgeConfig {
  from: string;
  to: string;
  condition?: string;
}

interface McpServer {
  name: string;
  type: 'stdio' | 'http' | 'sse';
  endpoint?: string;
  command?: string;
  args?: string;
}

interface StateVar {
  name: string;
  type: 'string' | 'integer' | 'float' | 'boolean';
}

interface ParallelGroup {
  group: string;
  nodes: string;
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

// ── Node Detail Panel ─────────────────────────────────────────────────────────

const NodeDetailPanel: React.FC<{
  node: NodeConfig;
  onChange: (n: NodeConfig) => void;
  stateKeys: string[];
}> = ({ node, onChange, stateKeys }) => {
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
            <FieldLabel hint="Conditional rules that determine which node to go to next">Routing Logic</FieldLabel>
            <button onClick={addRoute} className="text-xs px-2 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 rounded-lg transition-colors">
              + Add Rule
            </button>
          </div>
          <div className="space-y-2">
            {(node.routing_logic ?? []).map((r, i) => (
              <div key={i} className="flex gap-2 items-center">
                <Input value={r.condition} onChange={e => updateRoute(i, { ...r, condition: e.target.value })} placeholder="condition (e.g. task == 'research')" />
                <span className="text-slate-400 text-sm">→</span>
                <Input value={r.next} onChange={e => updateRoute(i, { ...r, next: e.target.value })} placeholder="next node id" className="w-36" />
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
    </div>
  );
};

// ── Live JSON Sidebar ─────────────────────────────────────────────────────────

const LiveJsonSidebar: React.FC<{ config: any }> = ({ config }) => {
  const [copied, setCopied] = useState(false);
  const text = useMemo(() => JSON.stringify(config, null, 2), [config]);

  const copy = () => {
    navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); });
  };

  return (
    <div className="w-56 flex-shrink-0 sticky top-4 self-start">
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
    </div>
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

  // ── Memory
  const [stmType, setStmType] = useState('graph_state');
  const [ltmType, setLtmType] = useState('sqlite');
  const [ltmProvider, setLtmProvider] = useState('sqlite');
  const [ltmCollection, setLtmCollection] = useState('memory');

  // ── Advanced
  const [parallelGroups, setParallelGroups] = useState<ParallelGroup[]>([]);
  const [maxRetries, setMaxRetries] = useState(3);
  const [retryIncrementState, setRetryIncrementState] = useState('retry_count');
  const [checkpointingEnabled, setCheckpointingEnabled] = useState(true);
  const [checkpointNodes, setCheckpointNodes] = useState<string[]>([]);
  const [obsTraceNodes, setObsTraceNodes] = useState(true);
  const [obsLogTransitions, setObsLogTransitions] = useState(true);
  const [obsCaptureOutputs, setObsCaptureOutputs] = useState(true);

  // ── Run
  const [runResult, setRunResult] = useState<any>(null);
  const [runLoading, setRunLoading] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  const { handleSave } = useWorkflowBuilder();

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

    if (ex?.state_schema && typeof ex.state_schema === 'object') {
      setStateSchema(Object.entries(ex.state_schema).map(([name, type]) => ({ name, type: type as any })));
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
      })));
      // Build edges from agent "next" fields
      const inferredEdges: EdgeConfig[] = (ex.agents as any[])
        .filter((a: any) => a.next && a.next !== 'END')
        .map((a: any) => ({ from: a.name || a.id || '', to: a.next, condition: '' }));
      if (inferredEdges.length > 0) setEdges(inferredEdges);
    }

    if (Array.isArray(ex?.edges)) {
      setEdges(ex.edges.map((e: any) => ({ from: e.from || '', to: e.to || '', condition: e.condition || '' })));
    }
    if (ex?.mcp_servers && typeof ex.mcp_servers === 'object') {
      setMcpServers(Object.entries(ex.mcp_servers).map(([name, cfg]: [string, any]) => ({
        name,
        type: cfg.type || 'http',
        endpoint: cfg.endpoint || '',
        command: cfg.command || '',
        args: Array.isArray(cfg.args) ? cfg.args.join(' ') : (cfg.args || ''),
      })));
    }
    if (ex?.runtime) {
      setMaxIterations(ex.runtime.max_iterations ?? 20);
      setCheckpointStore(ex.runtime.checkpoint_store ?? 'sqlite');
      setTracingEnabled(ex.runtime.observability?.tracing ?? true);
      setTracingProvider(ex.runtime.observability?.provider ?? 'logging');
    }
    if (ex?.memory) {
      setStmType(ex.memory.short_term?.type ?? 'graph_state');
      setLtmType(ex.memory.long_term?.type ?? 'sqlite');
      setLtmProvider(ex.memory.long_term?.provider ?? 'sqlite');
      setLtmCollection(ex.memory.long_term?.collection ?? 'memory');
    }
    if (Array.isArray(ex?.parallel_execution)) {
      setParallelGroups(ex.parallel_execution.map((g: any) => ({
        group: g.group || '',
        nodes: Array.isArray(g.nodes) ? g.nodes.join(', ') : '',
      })));
    }
    if (ex?.retry_policy) {
      setMaxRetries(ex.retry_policy.max_retries ?? 3);
      setRetryIncrementState(ex.retry_policy.increment_state ?? 'retry_count');
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
    const schema: Record<string, string> = {};
    stateSchema.forEach(v => { if (v.name) schema[v.name] = v.type; });

    const mcpObj: Record<string, any> = {};
    mcpServers.forEach(s => {
      if (!s.name) return;
      const cfg: any = { type: s.type };
      if (s.type === 'http' || s.type === 'sse') { if (s.endpoint) cfg.endpoint = s.endpoint; }
      if (s.type === 'stdio') {
        if (s.command) cfg.command = s.command;
        if (s.args) cfg.args = s.args.split(/\s+/).filter(Boolean);
      }
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
      return o;
    });

    const edgesOut = edges.filter(e => e.from && e.to).map(e => {
      const o: any = { from: e.from, to: e.to };
      if (e.condition) o.condition = e.condition;
      return o;
    });

    const parallelOut = parallelGroups.filter(g => g.group).map(g => ({
      group: g.group,
      nodes: g.nodes.split(',').map(s => s.trim()).filter(Boolean),
    }));

    return {
      graph_name: graphName || 'my_workflow',
      version,
      runtime: {
        max_iterations: maxIterations,
        checkpoint_store: checkpointStore,
        observability: { tracing: tracingEnabled, provider: tracingProvider },
      },
      memory: {
        short_term: { type: stmType },
        long_term: { type: ltmType, provider: ltmProvider, collection: ltmCollection },
      },
      ...(Object.keys(mcpObj).length > 0 ? { mcp_servers: mcpObj } : {}),
      ...(Object.keys(schema).length > 0 ? { state_schema: schema } : {}),
      nodes: nodesOut,
      edges: edgesOut,
      ...(parallelOut.length > 0 ? { parallel_execution: parallelOut } : {}),
      retry_policy: { max_retries: maxRetries, increment_state: retryIncrementState },
      checkpointing: { enabled: checkpointingEnabled, nodes: checkpointNodes },
      observability_hooks: {
        trace_nodes: obsTraceNodes,
        log_state_transitions: obsLogTransitions,
        capture_agent_outputs: obsCaptureOutputs,
      },
    };
  }, [
    graphName, version, stateSchema, nodes, edges, mcpServers,
    maxIterations, checkpointStore, tracingEnabled, tracingProvider,
    stmType, ltmType, ltmProvider, ltmCollection,
    parallelGroups, maxRetries, retryIncrementState,
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
          <div key={i} className="flex gap-3 items-center p-3 bg-slate-50 rounded-xl border border-slate-200">
            <Input value={v.name} onChange={e => setStateSchema(prev => prev.map((x, idx) => idx === i ? { ...x, name: e.target.value } : x))}
              placeholder="variable_name" className="flex-1" />
            <Select value={v.type} onChange={e => setStateSchema(prev => prev.map((x, idx) => idx === i ? { ...x, type: e.target.value as any } : x))}
              className="w-36">
              <option value="string">string</option>
              <option value="integer">integer</option>
              <option value="float">float</option>
              <option value="boolean">boolean</option>
            </Select>
            <button onClick={() => setStateSchema(prev => prev.filter((_, idx) => idx !== i))}
              className="text-slate-300 hover:text-rose-500 transition-colors px-2">
              <i className="fas fa-trash-alt text-sm"></i>
            </button>
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
            <NodeDetailPanel node={selectedNode} onChange={updateSelectedNode} stateKeys={stateKeys} />
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
      <p className="text-xs text-slate-400">Explicit edges connect nodes. Conditional edges fire only when the condition is met.</p>
      {edges.length === 0 && (
        <div className="py-10 text-center border-2 border-dashed border-slate-200 rounded-xl text-slate-400 text-sm">
          No edges defined. Nodes can also use their "next" field for simple routing.
        </div>
      )}
      <div className="space-y-2">
        {edges.map((e, i) => (
          <div key={i} className="flex gap-3 items-center p-3 bg-slate-50 rounded-xl border border-slate-200">
            <Select value={e.from} onChange={ev => setEdges(prev => prev.map((x, idx) => idx === i ? { ...x, from: ev.target.value } : x))} className="w-40">
              <option value="">from…</option>
              {nodeIds.map(id => <option key={id} value={id}>{id}</option>)}
            </Select>
            <i className="fas fa-arrow-right text-slate-400"></i>
            <Select value={e.to} onChange={ev => setEdges(prev => prev.map((x, idx) => idx === i ? { ...x, to: ev.target.value } : x))} className="w-40">
              <option value="">to…</option>
              {nodeIds.map(id => <option key={id} value={id}>{id}</option>)}
            </Select>
            <Input value={e.condition ?? ''} onChange={ev => setEdges(prev => prev.map((x, idx) => idx === i ? { ...x, condition: ev.target.value } : x))}
              placeholder="condition (optional)" className="flex-1" />
            <button onClick={() => setEdges(prev => prev.filter((_, idx) => idx !== i))}
              className="text-slate-300 hover:text-rose-500 transition-colors">
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
      try {
        await saveTemplate({ name: cfg.graph_name, description, example: cfg });
        setNotification({ type: 'success', msg: `Saved as template: ${cfg.graph_name}` });
      } catch (e: any) {
        setNotification({ type: 'error', msg: e?.response?.data?.detail || 'Save failed' });
      }
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

          {/* Flow diagram */}
          <div className="p-5 bg-slate-900 rounded-2xl">
            <p className="text-xs text-slate-400 font-bold uppercase tracking-widest mb-3">Flow Diagram</p>
            <pre className="text-xs text-emerald-300 font-mono leading-relaxed whitespace-pre-wrap">
              {buildFlowDiagram()}
            </pre>
          </div>

          {/* Actions */}
          <div className="space-y-3">
            <button onClick={handleSaveTemplate}
              className="w-full py-3 bg-white border-2 border-slate-200 hover:border-indigo-300 hover:bg-indigo-50 text-slate-700 hover:text-indigo-700 font-semibold rounded-xl flex items-center justify-center gap-2 transition-all">
              <i className="fas fa-save"></i> Save as Template
            </button>
            <button onClick={handleRun} disabled={runLoading}
              className="w-full py-3.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold rounded-xl flex items-center justify-center gap-2 transition-colors shadow-lg shadow-indigo-200">
              {runLoading
                ? <><i className="fas fa-spinner fa-spin"></i> Running...</>
                : <><i className="fas fa-play"></i> Run Workflow</>}
            </button>
          </div>
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

          {/* ── Right: live JSON sidebar */}
          <div className="p-4 border-l border-slate-200 bg-white">
            <LiveJsonSidebar config={config} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default BuilderView;
