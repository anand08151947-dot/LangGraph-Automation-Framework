
import React, { useEffect, useState } from 'react';
import { Card } from '../components/Shared';
import { getSystemHealth } from '../services/api';

// ─── Types ────────────────────────────────────────────────────────────────────
type Tab = 'overview' | 'builder' | 'schema' | 'api' | 'examples' | 'troubleshooting';

// ─── Pill Tab Bar ─────────────────────────────────────────────────────────────
const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'overview',         label: 'Overview',        icon: 'fa-house'          },
  { id: 'builder',          label: 'Builder Guide',   icon: 'fa-hammer'         },
  { id: 'schema',           label: 'JSON Schema',     icon: 'fa-code'           },
  { id: 'api',              label: 'API Reference',   icon: 'fa-plug'           },
  { id: 'examples',         label: 'Examples',        icon: 'fa-lightbulb'      },
  { id: 'troubleshooting',  label: 'Troubleshooting', icon: 'fa-triangle-exclamation' },
];

// ─── Accordion helpers ────────────────────────────────────────────────────────
interface AccordionProps {
  title: string;
  icon: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}
const Accordion: React.FC<AccordionProps> = ({ title, icon, open, onToggle, children }) => (
  <div className="border border-slate-200 rounded-xl overflow-hidden">
    <button
      onClick={onToggle}
      className="w-full flex items-center justify-between px-5 py-4 bg-slate-50 hover:bg-slate-100 transition-colors text-left"
    >
      <span className="flex items-center gap-3 font-semibold text-slate-800">
        <i className={`fas ${icon} text-indigo-500 w-4`}></i>
        {title}
      </span>
      <i className={`fas fa-chevron-down text-slate-400 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}></i>
    </button>
    {open && <div className="px-5 py-4 text-sm text-slate-700 space-y-3 bg-white">{children}</div>}
  </div>
);

// ─── Code block with Copy button ──────────────────────────────────────────────
const CopyCodeBlock: React.FC<{ title: string; description: string; code: string }> = ({ title, description, code }) => {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); });
  };
  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 bg-slate-800">
        <div>
          <p className="font-semibold text-white text-sm">{title}</p>
          <p className="text-slate-400 text-xs">{description}</p>
        </div>
        <button onClick={copy} className="flex items-center gap-2 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs rounded-lg transition-colors">
          <i className={`fas ${copied ? 'fa-check text-emerald-400' : 'fa-copy'}`}></i>
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <pre className="overflow-x-auto text-xs text-emerald-300 bg-slate-900 p-5 leading-relaxed">{code}</pre>
    </div>
  );
};

// ─── Method badge ─────────────────────────────────────────────────────────────
const METHOD_COLORS: Record<string, string> = {
  POST:   'bg-indigo-100 text-indigo-700',
  GET:    'bg-emerald-100 text-emerald-700',
  PUT:    'bg-amber-100  text-amber-700',
  DELETE: 'bg-rose-100   text-rose-700',
};
const EndpointRow: React.FC<{ method: string; path: string; desc: string }> = ({ method, path, desc }) => (
  <div className="flex items-start gap-4 p-3 rounded-xl bg-slate-50 border border-slate-100 font-mono text-sm">
    <span className={`shrink-0 px-2 py-0.5 rounded text-xs font-bold ${METHOD_COLORS[method] ?? 'bg-slate-200 text-slate-700'}`}>{method}</span>
    <div className="min-w-0">
      <span className="text-slate-800 font-semibold break-all">{path}</span>
      <p className="font-sans text-slate-500 text-xs mt-0.5">{desc}</p>
    </div>
  </div>
);

// ─── Schema table ─────────────────────────────────────────────────────────────
interface SchemaRow { field: string; type: string; desc: string; example: string }
const SchemaSection: React.FC<{ heading: string; rows: SchemaRow[] }> = ({ heading, rows }) => (
  <div>
    <h3 className="text-xs font-bold text-indigo-600 uppercase tracking-widest mb-2">{heading}</h3>
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-slate-50 text-slate-500 text-left">
            <th className="px-3 py-2 font-semibold w-1/4">Field path</th>
            <th className="px-3 py-2 font-semibold w-1/6">Type</th>
            <th className="px-3 py-2 font-semibold">Description</th>
            <th className="px-3 py-2 font-semibold w-1/5">Example</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r, i) => (
            <tr key={i} className="hover:bg-slate-50">
              <td className="px-3 py-2 font-mono text-indigo-700">{r.field}</td>
              <td className="px-3 py-2 font-mono text-amber-700">{r.type}</td>
              <td className="px-3 py-2 text-slate-600">{r.desc}</td>
              <td className="px-3 py-2 font-mono text-slate-500 break-all">{r.example}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);

// ═══════════════════════════════════════════════════════════════════════════════
// TAB CONTENT COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

// ─── Overview ────────────────────────────────────────────────────────────────
const OverviewTab: React.FC<{ health: any; healthError: string | null }> = ({ health, healthError }) => {
  const isHealthy = health && (health.status === 'ok' || health.status === 'healthy');
  const concepts = [
    { icon: 'fa-circle-nodes', title: 'Nodes & Edges', desc: 'Build directed graphs where each node is an agent, tool, or router. Edges define the flow with optional conditions.' },
    { icon: 'fa-database',     title: 'State Schema',  desc: 'A shared TypedDict-style object that flows through every node, carrying results and context across the workflow.' },
    { icon: 'fa-shield-halved',title: 'Guardrails',    desc: 'Per-node input/output filters for PII redaction, harmful content blocking, prompt-injection defence, and length limits.' },
    { icon: 'fa-bolt',         title: 'Pre-LLM Pipeline', desc: 'Grounding steps (tool calls + RAG) that run before the LLM to inject relevant context, reducing hallucination.' },
  ];
  return (
    <div className="space-y-6">
      {/* System Status */}
      <Card title="System Status">
        {healthError ? (
          <div className="flex items-center gap-3 p-3 bg-rose-50 border border-rose-200 rounded-xl">
            <div className="w-3 h-3 rounded-full bg-rose-500"></div>
            <p className="text-sm font-medium text-rose-700">Backend unreachable: {healthError}</p>
          </div>
        ) : health ? (
          <div className="flex items-center gap-4 p-3 bg-emerald-50 border border-emerald-200 rounded-xl">
            <div className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse"></div>
            <div>
              <p className="text-sm font-bold text-emerald-700">System {isHealthy ? 'Healthy' : 'Degraded'}</p>
              {health.version && <p className="text-xs text-slate-500">Version: {health.version}</p>}
              {health.status  && <p className="text-xs text-slate-500">Status: {health.status}</p>}
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-xl">
            <div className="w-3 h-3 rounded-full bg-slate-300 animate-pulse"></div>
            <p className="text-sm text-slate-500">Checking backend health…</p>
          </div>
        )}
      </Card>

      {/* What is this? */}
      <Card title="What is this?">
        <p className="text-slate-600 leading-relaxed">
          The <span className="font-semibold text-indigo-700">Agentic AI Workbench</span> is a config-driven, zero-code-wiring framework for building multi-agent LLM pipelines.
          You describe agents, tools, routing logic, memory, and guardrails in a single JSON document — the engine assembles and runs the LangGraph state-graph automatically.
          No manual graph wiring, no boilerplate.  Hot-swap behaviour by editing config.
        </p>
      </Card>

      {/* Quick Start */}
      <Card title="Quick-Start — 3 Steps">
        <ol className="space-y-4">
          {[
            { icon: 'fa-gear',      color: 'indigo', step: '1', title: 'Configure LLM in Settings', body: 'Point the backend at your LLM provider.  LM Studio on port 1234 is recommended for local runs — just load a model and hit "Test Connection".' },
            { icon: 'fa-hammer',    color: 'violet', step: '2', title: 'Pick or build a workflow template in Builder', body: 'Select an existing template (Research Pipeline, Enterprise Supervisor…) or drag-and-drop nodes to design your own. Use "Translate English → JSON" to describe your workflow in plain language.' },
            { icon: 'fa-rocket',    color: 'emerald',step: '3', title: 'Run it and download the generated code bundle', body: 'Hit Run, watch the live execution log, then click "Download Bundle" to get the deployable Python package with config, STM/LTM snapshots, and run artifacts.' },
          ].map(s => (
            <li key={s.step} className="flex gap-4">
              <div className={`shrink-0 w-10 h-10 rounded-xl bg-${s.color}-100 flex items-center justify-center`}>
                <i className={`fas ${s.icon} text-${s.color}-600`}></i>
              </div>
              <div>
                <p className="font-semibold text-slate-800">{s.title}</p>
                <p className="text-sm text-slate-500 mt-0.5">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </Card>

      {/* Key Concepts grid */}
      <div>
        <h2 className="text-sm font-bold text-slate-500 uppercase tracking-widest mb-4">Key Concepts</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {concepts.map(c => (
            <div key={c.title} className="p-5 border border-slate-200 rounded-xl bg-white hover:border-indigo-300 hover:shadow-sm transition-all">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-8 h-8 rounded-lg bg-indigo-50 flex items-center justify-center">
                  <i className={`fas ${c.icon} text-indigo-600 text-sm`}></i>
                </div>
                <p className="font-semibold text-slate-800">{c.title}</p>
              </div>
              <p className="text-sm text-slate-500 leading-relaxed">{c.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// ─── Builder Guide ────────────────────────────────────────────────────────────
const BUILDER_SECTIONS = [
  {
    id: 'overview', icon: 'fa-info-circle', title: 'Overview',
    body: (
      <div className="space-y-2">
        <p>Top-level metadata fields that identify the workflow:</p>
        <ul className="list-disc list-inside space-y-1 text-slate-600">
          <li><code className="bg-slate-100 px-1 rounded">graph_name</code> — unique workflow identifier (used as the run key and artifact folder name).</li>
          <li><code className="bg-slate-100 px-1 rounded">version</code> — semver string (e.g. <code className="bg-slate-100 px-1 rounded">"1.0.0"</code>); bump when breaking changes occur.</li>
          <li><code className="bg-slate-100 px-1 rounded">author</code> — optional author label for discovery.</li>
          <li><code className="bg-slate-100 px-1 rounded">tags</code> — array of strings for template search and filtering.</li>
        </ul>
      </div>
    ),
  },
  {
    id: 'state', icon: 'fa-database', title: 'State Schema',
    body: (
      <div className="space-y-2">
        <p>Shared TypedDict-style variables that flow through every node. All agents read from and write to this schema.</p>
        <p><strong>Supported types:</strong> <code className="bg-slate-100 px-1 rounded">string</code>, <code className="bg-slate-100 px-1 rounded">integer</code>, <code className="bg-slate-100 px-1 rounded">float</code>, <code className="bg-slate-100 px-1 rounded">boolean</code>, <code className="bg-slate-100 px-1 rounded">list</code>, <code className="bg-slate-100 px-1 rounded">dict</code>.</p>
        <p>Set <code className="bg-slate-100 px-1 rounded">default_value</code> to pre-populate the state before the first node runs.</p>
        <pre className="bg-slate-900 text-emerald-300 text-xs p-3 rounded-lg overflow-x-auto">{`"state_schema": {
  "task":   { "type": "string",  "default_value": "",    "description": "The user's request" },
  "result": { "type": "string",  "default_value": "",    "description": "Final output" },
  "score":  { "type": "float",   "default_value": "0.0", "description": "Confidence 0–1" }
}`}</pre>
      </div>
    ),
  },
  {
    id: 'nodes', icon: 'fa-circle-nodes', title: 'Nodes',
    body: (
      <div className="space-y-2">
        <p>Each node is a unit of work. Key fields:</p>
        <ul className="list-disc list-inside space-y-1 text-slate-600">
          <li><code className="bg-slate-100 px-1 rounded">id</code> — unique node name.</li>
          <li><code className="bg-slate-100 px-1 rounded">type</code> — <code className="bg-slate-100 px-1 rounded">agent</code> | <code className="bg-slate-100 px-1 rounded">tool_node</code> | <code className="bg-slate-100 px-1 rounded">conditional</code> | <code className="bg-slate-100 px-1 rounded">human_node</code>.</li>
          <li><code className="bg-slate-100 px-1 rounded">system_prompt</code> — LLM persona / instructions (agent nodes only).</li>
          <li><code className="bg-slate-100 px-1 rounded">llm_config</code> — <code className="bg-slate-100 px-1 rounded">temperature</code>, <code className="bg-slate-100 px-1 rounded">max_tokens</code> overrides.</li>
          <li><code className="bg-slate-100 px-1 rounded">pre_llm</code> — tool calls + RAG run before the LLM call.</li>
          <li><code className="bg-slate-100 px-1 rounded">context.sources</code> — pull from <code className="bg-slate-100 px-1 rounded">previous_node</code>, <code className="bg-slate-100 px-1 rounded">stm</code>, <code className="bg-slate-100 px-1 rounded">ltm</code>, or <code className="bg-slate-100 px-1 rounded">pre_llm</code>.</li>
          <li><code className="bg-slate-100 px-1 rounded">output_schema</code> — <code className="bg-slate-100 px-1 rounded">format</code> (json/text) + <code className="bg-slate-100 px-1 rounded">state_key</code> to write the result into.</li>
          <li><code className="bg-slate-100 px-1 rounded">guardrails</code> — per-node output safety filters.</li>
          <li><code className="bg-slate-100 px-1 rounded">routing_logic</code> — ordered condition→next array for in-node routing.</li>
        </ul>
        <p className="text-slate-500 text-xs mt-2"><strong>Types:</strong> <em>agent</em> = calls LLM · <em>tool_node</em> = runs tools without LLM · <em>conditional</em> = pure routing · <em>human_node</em> = pauses for approval.</p>
      </div>
    ),
  },
  {
    id: 'edges', icon: 'fa-arrow-right', title: 'Edges',
    body: (
      <div className="space-y-2">
        <p>Explicit graph connections between nodes.</p>
        <ul className="list-disc list-inside space-y-1 text-slate-600">
          <li><code className="bg-slate-100 px-1 rounded">from</code> / <code className="bg-slate-100 px-1 rounded">to</code> — node IDs.</li>
          <li><code className="bg-slate-100 px-1 rounded">condition</code> — optional Python-style expression evaluated at runtime using state fields.</li>
          <li><code className="bg-slate-100 px-1 rounded">label</code> — optional display label for graph visualisations.</li>
        </ul>
        <p className="font-medium text-slate-700 mt-2">Example conditions:</p>
        <pre className="bg-slate-900 text-emerald-300 text-xs p-3 rounded-lg overflow-x-auto">{`task == "research"
confidence_score >= 0.7
retry_count > 3
approval_required == true`}</pre>
        <p className="text-xs text-slate-500">In-node routing uses <code className="bg-slate-100 px-1 rounded">routing_logic</code> (evaluated top-to-bottom); explicit edges are evaluated by the graph runtime.</p>
      </div>
    ),
  },
  {
    id: 'mcp', icon: 'fa-server', title: 'MCP Servers',
    body: (
      <div className="space-y-2">
        <p>Model Context Protocol servers expose tools to agents. Define them in the top-level <code className="bg-slate-100 px-1 rounded">mcp_servers</code> object; agents reference server names in their <code className="bg-slate-100 px-1 rounded">tools</code> list.</p>
        <p><strong>Server types:</strong></p>
        <ul className="list-disc list-inside space-y-1 text-slate-600">
          <li><code className="bg-slate-100 px-1 rounded">stdio</code> — subprocess command + args array.</li>
          <li><code className="bg-slate-100 px-1 rounded">sse</code> — server-sent events URL.</li>
          <li><code className="bg-slate-100 px-1 rounded">http</code> — REST endpoint.</li>
        </ul>
        <p><strong>Fields:</strong> <code className="bg-slate-100 px-1 rounded">type</code>, <code className="bg-slate-100 px-1 rounded">command</code>, <code className="bg-slate-100 px-1 rounded">args</code>, <code className="bg-slate-100 px-1 rounded">endpoint</code>, <code className="bg-slate-100 px-1 rounded">description</code>, <code className="bg-slate-100 px-1 rounded">timeout_ms</code>, <code className="bg-slate-100 px-1 rounded">auth_header</code>.</p>
      </div>
    ),
  },
  {
    id: 'runtime', icon: 'fa-microchip', title: 'Runtime & Memory',
    body: (
      <div className="space-y-3">
        <div>
          <p className="font-medium text-slate-800 mb-1">runtime</p>
          <ul className="list-disc list-inside space-y-1 text-slate-600 text-xs">
            <li><code className="bg-slate-100 px-1 rounded">max_iterations</code> — graph loop limit (default 20).</li>
            <li><code className="bg-slate-100 px-1 rounded">timeout_seconds</code> — wall-clock limit per run.</li>
            <li><code className="bg-slate-100 px-1 rounded">checkpoint_store</code> — <code className="bg-slate-100 px-1 rounded">sqlite</code> | <code className="bg-slate-100 px-1 rounded">postgres</code> | <code className="bg-slate-100 px-1 rounded">memory</code>.</li>
            <li><code className="bg-slate-100 px-1 rounded">error_policy</code> — <code className="bg-slate-100 px-1 rounded">fail_fast</code> | <code className="bg-slate-100 px-1 rounded">continue</code> | <code className="bg-slate-100 px-1 rounded">retry</code>.</li>
          </ul>
        </div>
        <div>
          <p className="font-medium text-slate-800 mb-1">memory</p>
          <ul className="list-disc list-inside space-y-1 text-slate-600 text-xs">
            <li><code className="bg-slate-100 px-1 rounded">short_term</code> — <code className="bg-slate-100 px-1 rounded">graph_state</code> (default) or <code className="bg-slate-100 px-1 rounded">redis</code>.</li>
            <li><code className="bg-slate-100 px-1 rounded">long_term</code> — <code className="bg-slate-100 px-1 rounded">sqlite</code> (default), <code className="bg-slate-100 px-1 rounded">chroma</code>, <code className="bg-slate-100 px-1 rounded">milvus</code>, <code className="bg-slate-100 px-1 rounded">pinecone</code>.</li>
          </ul>
        </div>
      </div>
    ),
  },
  {
    id: 'advanced', icon: 'fa-sliders', title: 'Advanced',
    body: (
      <div className="space-y-2">
        <ul className="list-disc list-inside space-y-1 text-slate-600">
          <li><code className="bg-slate-100 px-1 rounded">parallel_execution</code> — groups of node IDs to run concurrently.</li>
          <li><code className="bg-slate-100 px-1 rounded">retry_policy</code> — <code className="bg-slate-100 px-1 rounded">max_retries</code>, <code className="bg-slate-100 px-1 rounded">backoff_strategy</code> (<code className="bg-slate-100 px-1 rounded">fixed</code>/<code className="bg-slate-100 px-1 rounded">exponential</code>), <code className="bg-slate-100 px-1 rounded">retry_on</code> event list.</li>
          <li><code className="bg-slate-100 px-1 rounded">checkpointing.nodes</code> — list of node IDs where state is snapshotted so runs can be resumed.</li>
        </ul>
      </div>
    ),
  },
  {
    id: 'prellm', icon: 'fa-bolt', title: 'Pre-LLM Pipeline',
    body: (
      <div className="space-y-2">
        <p>Steps executed <em>before</em> the LLM call to inject grounding data:</p>
        <ul className="list-disc list-inside space-y-1 text-slate-600">
          <li><strong>tool_calls</strong> — invoke MCP tools; results are concatenated into the context window.</li>
          <li><strong>rag</strong> — semantic/keyword search. Providers: <code className="bg-slate-100 px-1 rounded">ltm</code>, <code className="bg-slate-100 px-1 rounded">chroma</code>, <code className="bg-slate-100 px-1 rounded">milvus</code>, <code className="bg-slate-100 px-1 rounded">local_files</code>.</li>
        </ul>
        <p>Use <code className="bg-slate-100 px-1 rounded">{'{state.VAR}'}</code> in <code className="bg-slate-100 px-1 rounded">input_template</code> / <code className="bg-slate-100 px-1 rounded">query_template</code> to reference live state values.</p>
        <pre className="bg-slate-900 text-emerald-300 text-xs p-3 rounded-lg overflow-x-auto">{`"pre_llm": {
  "rag": {
    "enabled": true,
    "provider": "ltm",
    "query_template": "{state.task}",
    "top_k": 5
  }
}`}</pre>
      </div>
    ),
  },
  {
    id: 'guardrails', icon: 'fa-shield-halved', title: 'Guardrails',
    body: (
      <div className="space-y-3">
        <div>
          <p className="font-medium text-slate-800 mb-1">Input guardrails <span className="text-xs font-normal text-slate-500">(applied to context before LLM call)</span></p>
          <ul className="list-disc list-inside space-y-1 text-slate-600 text-xs">
            <li>PII detection / redaction</li>
            <li>Prompt injection blocking</li>
            <li>Secrets detection</li>
            <li>Profanity filter</li>
            <li>Context length limits (<code className="bg-slate-100 px-1 rounded">max_chars</code>, <code className="bg-slate-100 px-1 rounded">on_exceed: truncate</code>)</li>
          </ul>
        </div>
        <div>
          <p className="font-medium text-slate-800 mb-1">Output guardrails <span className="text-xs font-normal text-slate-500">(applied to LLM response)</span></p>
          <ul className="list-disc list-inside space-y-1 text-slate-600 text-xs">
            <li>PII · Harmful content · Self-harm · Hate speech · Regulated advice</li>
          </ul>
        </div>
        <p className="text-xs text-slate-500"><strong>Actions:</strong> <code className="bg-slate-100 px-1 rounded">block</code> (stops execution) · <code className="bg-slate-100 px-1 rounded">redact</code> (masks) · <code className="bg-slate-100 px-1 rounded">warn</code> (logs only).</p>
      </div>
    ),
  },
];

const BuilderGuideTab: React.FC = () => {
  const [open, setOpen] = useState<Record<string, boolean>>({ overview: true });
  const toggle = (id: string) => setOpen(prev => ({ ...prev, [id]: !prev[id] }));
  return (
    <div className="space-y-3">
      {BUILDER_SECTIONS.map(s => (
        <Accordion key={s.id} title={s.title} icon={s.icon} open={!!open[s.id]} onToggle={() => toggle(s.id)}>
          {s.body}
        </Accordion>
      ))}
    </div>
  );
};

// ─── JSON Schema ──────────────────────────────────────────────────────────────
const JSON_SCHEMA_SECTIONS: { heading: string; rows: SchemaRow[] }[] = [
  {
    heading: 'Top-level',
    rows: [
      { field: 'graph_name', type: 'string', desc: 'Unique workflow identifier', example: '"ResearchPipeline"' },
      { field: 'version',    type: 'string', desc: 'Semver string',              example: '"1.0.0"' },
      { field: 'author',     type: 'string', desc: 'Author label',               example: '"Alice"' },
      { field: 'tags',       type: 'array',  desc: 'Discovery tags',             example: '["nlp","rag"]' },
    ],
  },
  {
    heading: 'Runtime',
    rows: [
      { field: 'runtime.max_iterations',  type: 'integer', desc: 'Max graph loop iterations',  example: '20' },
      { field: 'runtime.timeout_seconds', type: 'integer', desc: 'Wall-clock limit per run',   example: '120' },
      { field: 'runtime.checkpoint_store',type: 'string',  desc: 'sqlite | postgres | memory', example: '"sqlite"' },
      { field: 'runtime.error_policy',    type: 'string',  desc: 'fail_fast | continue | retry', example: '"retry"' },
    ],
  },
  {
    heading: 'Memory',
    rows: [
      { field: 'memory.short_term', type: 'string', desc: 'graph_state | redis',               example: '"graph_state"' },
      { field: 'memory.long_term',  type: 'string', desc: 'sqlite | chroma | milvus | pinecone', example: '"sqlite"' },
    ],
  },
  {
    heading: 'State Schema',
    rows: [
      { field: 'state_schema.<key>.type',          type: 'string', desc: 'string|integer|float|boolean|list|dict', example: '"string"' },
      { field: 'state_schema.<key>.default_value', type: 'string', desc: 'Pre-fill value',                         example: '"0.0"' },
      { field: 'state_schema.<key>.description',   type: 'string', desc: 'Human label',                            example: '"Confidence"' },
    ],
  },
  {
    heading: 'Node fields',
    rows: [
      { field: 'nodes[].id',             type: 'string', desc: 'Unique node name',                            example: '"Planner"' },
      { field: 'nodes[].type',           type: 'string', desc: 'agent|tool_node|conditional|human_node',      example: '"agent"' },
      { field: 'nodes[].system_prompt',  type: 'string', desc: 'LLM persona / instructions',                  example: '"Analyze the task…"' },
      { field: 'nodes[].next',           type: 'string', desc: 'Default next node ID or END',                 example: '"Researcher"' },
      { field: 'nodes[].tools',          type: 'array',  desc: 'MCP server names to bind',                    example: '["search","calc"]' },
      { field: 'nodes[].checkpoint',     type: 'boolean',desc: 'Save checkpoint at this node',                example: 'true' },
      { field: 'nodes[].routing_logic',  type: 'array',  desc: 'Ordered condition→next rules',                example: '[{"condition":"score>0.8","next":"END"}]' },
      { field: 'nodes[].llm_config.temperature', type: 'number', desc: 'Sampling temperature',                example: '0.2' },
      { field: 'nodes[].llm_config.max_tokens',  type: 'integer','desc': 'Max response tokens',               example: '1024' },
      { field: 'nodes[].output_schema.format',   type: 'string', desc: 'json | text',                         example: '"json"' },
      { field: 'nodes[].output_schema.state_key',type: 'string', desc: 'State field to write output into',    example: '"result"' },
    ],
  },
  {
    heading: 'Pre-LLM',
    rows: [
      { field: 'nodes[].pre_llm.rag.enabled',        type: 'boolean', desc: 'Enable RAG step',                   example: 'true' },
      { field: 'nodes[].pre_llm.rag.provider',        type: 'string',  desc: 'ltm|chroma|milvus|local_files',     example: '"ltm"' },
      { field: 'nodes[].pre_llm.rag.query_template',  type: 'string',  desc: 'Query with {state.VAR} tokens',     example: '"{state.task}"' },
      { field: 'nodes[].pre_llm.rag.top_k',           type: 'integer', desc: 'Max results to retrieve',           example: '5' },
      { field: 'nodes[].pre_llm.tool_calls[].server', type: 'string',  desc: 'MCP server name',                   example: '"search"' },
      { field: 'nodes[].pre_llm.tool_calls[].tool',   type: 'string',  desc: 'Tool name on that server',          example: '"web_search"' },
    ],
  },
  {
    heading: 'Context Sources',
    rows: [
      { field: 'nodes[].context.sources[].type', type: 'string', desc: 'previous_node|stm|ltm|pre_llm', example: '"stm"' },
      { field: 'nodes[].context.sources[].keys', type: 'array',  desc: 'State keys to pull (stm type)', example: '["task","result"]' },
    ],
  },
  {
    heading: 'Guardrails',
    rows: [
      { field: 'nodes[].guardrails.pii.enabled',      type: 'boolean', desc: 'PII detection',                    example: 'true' },
      { field: 'nodes[].guardrails.pii.action',        type: 'string',  desc: 'block|redact|warn',                example: '"redact"' },
      { field: 'nodes[].guardrails.harmful.enabled',   type: 'boolean', desc: 'Harmful content filter',           example: 'true' },
      { field: 'nodes[].guardrails.harmful.action',    type: 'string',  desc: 'block|warn',                       example: '"block"' },
      { field: 'nodes[].context.input_guardrails.context_length.max_chars', type: 'integer', desc: 'Input length limit', example: '4000' },
    ],
  },
  {
    heading: 'Edges',
    rows: [
      { field: 'edges[].from',      type: 'string', desc: 'Source node ID',          example: '"Planner"' },
      { field: 'edges[].to',        type: 'string', desc: 'Target node ID or END',   example: '"Researcher"' },
      { field: 'edges[].condition', type: 'string', desc: 'Python-style expression', example: '"score >= 0.7"' },
      { field: 'edges[].label',     type: 'string', desc: 'Display label',           example: '"high confidence"' },
    ],
  },
  {
    heading: 'Advanced',
    rows: [
      { field: 'retry_policy.max_retries',      type: 'integer', desc: 'Retry attempts',                example: '3' },
      { field: 'retry_policy.backoff_strategy', type: 'string',  desc: 'fixed | exponential',           example: '"exponential"' },
      { field: 'parallel_execution',            type: 'array',   desc: 'Groups of node IDs to run concurrently', example: '[["ResearchAgent","CodeAgent"]]' },
      { field: 'checkpointing.nodes',           type: 'array',   desc: 'Node IDs where state is saved', example: '["HumanApproval"]' },
    ],
  },
];

const JsonSchemaTab: React.FC = () => {
  const [copied, setCopied] = useState(false);
  const copyUrl = () => {
    navigator.clipboard.writeText('GET /openapi.json').then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); });
  };
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-slate-600 text-sm">Structured reference of every supported field. Use this alongside the Builder to understand available options.</p>
        <button onClick={copyUrl} className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg transition-colors">
          <i className={`fas ${copied ? 'fa-check' : 'fa-copy'}`}></i>
          {copied ? 'Copied!' : 'Copy Full Schema URL'}
        </button>
      </div>
      {JSON_SCHEMA_SECTIONS.map(s => (
        <SchemaSection key={s.heading} heading={s.heading} rows={s.rows} />
      ))}
    </div>
  );
};

// ─── API Reference ────────────────────────────────────────────────────────────
const API_ENDPOINTS = [
  { method: 'POST', path: '/orchestrate_async',      desc: 'Start async workflow run' },
  { method: 'GET',  path: '/status/{run_id}',         desc: 'Poll run status' },
  { method: 'GET',  path: '/runs',                    desc: 'List all runs' },
  { method: 'GET',  path: '/run/{run_id}',            desc: 'Single run detail' },
  { method: 'POST', path: '/resume/{run_id}',         desc: 'Resume paused (human_node) run' },
  { method: 'GET',  path: '/approval/{run_id}',       desc: 'Get checkpoint info for approval' },
  { method: 'POST', path: '/english_to_json',         desc: 'Translate English → workflow JSON (LM Studio)' },
  { method: 'POST', path: '/customize_json_llm',      desc: 'Customize existing JSON with instructions' },
  { method: 'POST', path: '/generate_code',           desc: 'Generate deployable Python from config' },
  { method: 'GET',  path: '/templates',               desc: 'List all templates' },
  { method: 'POST', path: '/save_template',           desc: 'Save / version a custom template' },
  { method: 'GET',  path: '/memory/stm/{session}',    desc: 'Read short-term memory' },
  { method: 'GET',  path: '/memory/ltm/{session}',    desc: 'Read long-term memory history' },
  { method: 'POST', path: '/llm/test',                desc: 'Test LLM provider connectivity' },
  { method: 'PUT',  path: '/config/llm',              desc: 'Save LLM provider config' },
  { method: 'GET',  path: '/config',                  desc: 'Read current config' },
  { method: 'GET',  path: '/health',                  desc: 'System health check' },
  { method: 'GET',  path: '/artifacts',               desc: 'List run artifacts' },
];

const ApiReferenceTab: React.FC = () => (
  <div className="space-y-3">
    <p className="text-sm text-slate-500">All endpoints are relative to the backend base URL (default <code className="bg-slate-100 px-1 rounded">http://localhost:8000</code>).</p>
    {API_ENDPOINTS.map((e, i) => (
      <EndpointRow key={i} method={e.method} path={e.path} desc={e.desc} />
    ))}
  </div>
);

// ─── Examples ─────────────────────────────────────────────────────────────────
const EXAMPLES = [
  {
    title: 'Research Pipeline',
    description: 'Two-agent pipeline: Planner breaks the task into steps; Researcher uses RAG against LTM to gather context.',
    code: JSON.stringify({
      graph_name: 'ResearchPipeline',
      version: '1.0',
      state_schema: { task: { type: 'string' }, result: { type: 'string' } },
      nodes: [
        { id: 'Planner', type: 'agent', system_prompt: 'Break the task into steps', next: 'Researcher' },
        {
          id: 'Researcher', type: 'agent', system_prompt: 'Research the topic thoroughly',
          pre_llm: { rag: { enabled: true, provider: 'ltm', query_template: '{state.task}', top_k: 5 } },
          output_schema: { format: 'json', state_key: 'result' }, next: 'END',
        },
      ],
      edges: [{ from: 'Planner', to: 'Researcher' }],
    }, null, 2),
  },
  {
    title: 'Enterprise Supervisor Workflow',
    description: 'Multi-agent supervisor pattern with reflection loop, human approval checkpoint, and exponential retry policy.',
    code: JSON.stringify({
      graph_name: 'Enterprise_Agent_Workflow',
      version: '1.0',
      state_schema: {
        task:              { type: 'string' },
        confidence_score:  { type: 'float',   default_value: '0.0'   },
        retry_count:       { type: 'integer',  default_value: '0'     },
        approval_required: { type: 'boolean',  default_value: 'false' },
      },
      nodes: [
        { id: 'Planner',       type: 'agent',      system_prompt: 'Analyze the request and plan the workflow', next: 'Supervisor' },
        { id: 'Supervisor',    type: 'agent',      system_prompt: 'Route to the right agent',
          routing_logic: [
            { condition: "task == 'research'", next: 'ResearchAgent' },
            { condition: "task == 'code'",     next: 'CodeAgent'     },
          ],
        },
        { id: 'ResearchAgent', type: 'agent',      system_prompt: 'Research thoroughly',      next: 'ReflectionAgent' },
        { id: 'CodeAgent',     type: 'agent',      system_prompt: 'Write clean code',         next: 'ReflectionAgent' },
        { id: 'ReflectionAgent', type: 'agent',    system_prompt: 'Evaluate output quality',
          routing_logic: [
            { condition: 'confidence_score >= 0.7', next: 'Executor'    },
            { condition: 'confidence_score < 0.7',  next: 'Supervisor'  },
          ],
        },
        { id: 'HumanApproval', type: 'human_node', checkpoint: true, next: 'Executor' },
        { id: 'Executor',      type: 'agent',      system_prompt: 'Execute the approved action', next: 'END' },
      ],
      edges: [
        { from: 'Planner',  to: 'Supervisor' },
        { from: 'Executor', to: 'END'        },
      ],
      retry_policy: { max_retries: 3, backoff_strategy: 'exponential' },
    }, null, 2),
  },
  {
    title: 'Safe Data Pipeline with Guardrails',
    description: 'Single ingester node with PII redaction input guardrail, harmful content output blocker, and context length limit.',
    code: JSON.stringify({
      graph_name: 'SafeDataPipeline',
      version: '1.0',
      state_schema: { input_data: { type: 'string' }, processed: { type: 'string' } },
      nodes: [
        {
          id: 'Ingester', type: 'agent', system_prompt: 'Extract key information from the input',
          context: {
            sources: [{ type: 'stm', keys: ['input_data'] }],
            input_guardrails: {
              pii:            { enabled: true, action: 'redact' },
              context_length: { enabled: true, max_chars: 4000, on_exceed: 'truncate' },
            },
          },
          guardrails: {
            pii:     { enabled: true, action: 'redact' },
            harmful: { enabled: true, action: 'block'  },
          },
          output_schema: { format: 'json', state_key: 'processed' },
          next: 'END',
        },
      ],
      edges: [],
    }, null, 2),
  },
];

const ExamplesTab: React.FC = () => (
  <div className="space-y-6">
    {EXAMPLES.map(ex => (
      <CopyCodeBlock key={ex.title} title={ex.title} description={ex.description} code={ex.code} />
    ))}
  </div>
);

// ─── Troubleshooting ──────────────────────────────────────────────────────────
const TROUBLESHOOTING = [
  {
    id: 'lmstudio', title: 'LM Studio not responding',
    body: (
      <ul className="list-disc list-inside space-y-1 text-slate-600">
        <li>Check LM Studio is running on port <strong>1234</strong>.</li>
        <li>Verify the model is loaded (green dot in LM Studio).</li>
        <li>Test with <strong>Settings → Test Connection</strong>.</li>
        <li>The backend tries the chat endpoint first, then falls back to completions automatically.</li>
      </ul>
    ),
  },
  {
    id: 'orch', title: '"Orchestrator not available" error',
    body: (
      <div className="space-y-1">
        <p className="text-slate-600">Run in your virtual environment then restart the backend:</p>
        <pre className="bg-slate-900 text-emerald-300 text-xs p-3 rounded-lg">pip install langgraph langchain-core</pre>
      </div>
    ),
  },
  {
    id: 'validation', title: 'Generated JSON fails validation',
    body: (
      <ul className="list-disc list-inside space-y-1 text-slate-600">
        <li>The schema requires <code className="bg-slate-100 px-1 rounded">graph_name</code> and <code className="bg-slate-100 px-1 rounded">nodes</code> (not <code className="bg-slate-100 px-1 rounded">agents</code> for new templates).</li>
        <li>Each node needs <code className="bg-slate-100 px-1 rounded">id</code> and <code className="bg-slate-100 px-1 rounded">type</code>.</li>
        <li>Use the Builder tab to generate valid JSON and copy it from there.</li>
      </ul>
    ),
  },
  {
    id: 'template', title: 'Template not appearing in Builder',
    body: (
      <ul className="list-disc list-inside space-y-1 text-slate-600">
        <li>Templates must be in <code className="bg-slate-100 px-1 rounded">prompt_templates/</code> as <code className="bg-slate-100 px-1 rounded">.json</code> files, OR saved via <code className="bg-slate-100 px-1 rounded">POST /save_template</code>.</li>
        <li>Re-seed by restarting the backend — it scans the directory on startup.</li>
      </ul>
    ),
  },
  {
    id: 'rag', title: 'RAG returns no results',
    body: (
      <ul className="list-disc list-inside space-y-1 text-slate-600">
        <li>LTM-based RAG only finds results if the session has run before (LTM is populated by prior runs).</li>
        <li>For new sessions use <code className="bg-slate-100 px-1 rounded">local_files</code> provider with a documents directory.</li>
        <li>For semantic search, install ChromaDB: <code className="bg-slate-100 px-1 rounded">pip install chromadb</code>.</li>
      </ul>
    ),
  },
  {
    id: 'human', title: 'Human approval run is stuck',
    body: (
      <div className="space-y-1 text-slate-600">
        <p>1. Call <code className="bg-slate-100 px-1 rounded">GET /approval/{'{run_id}'}</code> to inspect the checkpoint.</p>
        <p>2. Then resume:</p>
        <pre className="bg-slate-900 text-emerald-300 text-xs p-3 rounded-lg">{`POST /resume/{run_id}
{ "config_json": {...}, "approval_input": { "approved": true } }`}</pre>
      </div>
    ),
  },
  {
    id: 'build', title: 'Frontend build errors',
    body: (
      <div className="space-y-1">
        <p className="text-slate-600">Ensure Node.js ≥ 18, then:</p>
        <pre className="bg-slate-900 text-emerald-300 text-xs p-3 rounded-lg">cd frontend && npm install && npm run build</pre>
      </div>
    ),
  },
];

const TroubleshootingTab: React.FC = () => {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const toggle = (id: string) => setOpen(prev => ({ ...prev, [id]: !prev[id] }));
  return (
    <div className="space-y-3">
      {TROUBLESHOOTING.map(t => (
        <Accordion key={t.id} title={t.title} icon="fa-circle-exclamation" open={!!open[t.id]} onToggle={() => toggle(t.id)}>
          {t.body}
        </Accordion>
      ))}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════
const HelpView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [health, setHealth] = useState<any>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  useEffect(() => {
    getSystemHealth()
      .then(setHealth)
      .catch((e: any) => setHealthError(e?.message || 'Unable to reach backend'));
  }, []);

  const renderTab = () => {
    switch (activeTab) {
      case 'overview':        return <OverviewTab health={health} healthError={healthError} />;
      case 'builder':         return <BuilderGuideTab />;
      case 'schema':          return <JsonSchemaTab />;
      case 'api':             return <ApiReferenceTab />;
      case 'examples':        return <ExamplesTab />;
      case 'troubleshooting': return <TroubleshootingTab />;
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6 animate-in fade-in duration-500">
      {/* Header */}
      <div className="space-y-1">
        <h1 className="text-3xl font-bold text-slate-800">Documentation & Resources</h1>
        <p className="text-slate-500">Master the Agentic AI Workbench — guides, schema reference, and live examples.</p>
      </div>

      {/* Pill tab bar */}
      <div className="flex flex-wrap gap-2 p-1 bg-slate-100 rounded-2xl">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all duration-200
              ${activeTab === t.id
                ? 'bg-white text-indigo-700 shadow-sm shadow-slate-200 font-semibold'
                : 'text-slate-500 hover:text-slate-800 hover:bg-white/60'
              }`}
          >
            <i className={`fas ${t.icon} text-xs`}></i>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>{renderTab()}</div>
    </div>
  );
};

export default HelpView;
