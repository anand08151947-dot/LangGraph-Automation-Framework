# Minimal stub of LangGraph's StateGraph and END sentinel for testing/offline use.
# Implements the real LangGraph API surface used by graph_factory.py and orchestrator.py.

END = "__end__"


class _StateProxy:
    """Wraps a state dict with attribute-style access for backward compatibility.

    Old tests access state as `state.sender`, `state.messages`, etc.
    New code uses dict access; both are supported via this proxy.
    """
    def __init__(self, data: dict):
        object.__setattr__(self, '_data', dict(data))

    def __getattr__(self, key):
        try:
            return object.__getattribute__(self, '_data')[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, val):
        object.__getattribute__(self, '_data')[key] = val

    def __repr__(self):
        return f"StateProxy({object.__getattribute__(self, '_data')})"


class StateGraph:
    def __init__(self, state_cls):
        self.state_cls = state_cls
        self._nodes = []          # ordered list of (name, func)
        self._simple_edges = {}   # src -> dst
        self._cond_edges = {}     # src -> (func, mapping)
        self._entry_point = None

    def add_node(self, name, func):
        self._nodes.append((name, func))

    def add_edge(self, src, dst):
        self._simple_edges[src] = dst

    def add_conditional_edges(self, src, routing_func, mapping):
        """routing_func(state) -> label; mapping[label] -> next_node."""
        self._cond_edges[src] = (routing_func, mapping)

    def set_entry_point(self, name):
        self._entry_point = name

    def set_finish_point(self, name):
        self._simple_edges[name] = END

    def compile(self):
        nodes = {name: func for name, func in self._nodes}
        simple_edges = dict(self._simple_edges)
        cond_edges = dict(self._cond_edges)
        entry = self._entry_point or (self._nodes[0][0] if self._nodes else None)

        class CompiledGraph:
            def __init__(self, nodes, simple_edges, cond_edges, entry):
                self.nodes = nodes
                self.simple_edges = simple_edges
                self.cond_edges = cond_edges
                self.entry = entry

            def _run_steps(self, initial_state):
                """Generator that yields (node_name, updated_state_dict) per step."""
                state = dict(initial_state) if isinstance(initial_state, dict) else {}
                current = self.entry
                visited = 0
                max_steps = 100  # safety cap
                while current and current not in (END, "__end__") and visited < max_steps:
                    node_fn = self.nodes.get(current)
                    if node_fn is None:
                        break
                    result = node_fn(state)
                    if isinstance(result, dict):
                        state = result
                    yield current, state
                    # Determine next node
                    if current in self.cond_edges:
                        routing_func, mapping = self.cond_edges[current]
                        label = routing_func(state)
                        nxt = mapping.get(label, END)
                    elif current in self.simple_edges:
                        nxt = self.simple_edges[current]
                    else:
                        nxt = END
                    current = nxt
                    visited += 1

            def stream(self, initial_state):
                """Yield {node_name: state_dict} per executed node (real LangGraph API)."""
                for node_name, state in self._run_steps(initial_state):
                    yield {node_name: state}

            def invoke(self, initial_state):
                """Run to completion, return final state dict (real LangGraph API)."""
                final = dict(initial_state) if isinstance(initial_state, dict) else {}
                for _, state in self._run_steps(initial_state):
                    final = state
                return final

            def iter_run(self, initial_state=None):
                """Legacy API: yield _StateProxy objects per step for backward compat."""
                # Provide sensible defaults matching the old AgentState defaults
                base: dict = {"messages": [], "sender": "", "metadata": {}, "_step_count": 0}
                if isinstance(initial_state, dict):
                    base.update(initial_state)
                for _, state in self._run_steps(base):
                    yield _StateProxy(state)

        return CompiledGraph(nodes, simple_edges, cond_edges, entry)


