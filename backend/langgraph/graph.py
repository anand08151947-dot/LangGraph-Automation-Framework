# Minimal stub of LangGraph's StateGraph and END sentinel for testing

END = object()

class StateGraph:
    def __init__(self, state_cls):
        self.state_cls = state_cls
        self._nodes = []  # list of (name, func)
        self._edges = {}  # src -> dst

    def add_node(self, name, func):
        self._nodes.append((name, func))

    def add_edge(self, src, dst):
        self._edges[src] = dst

    def compile(self):
        # Return a simple runner with iter_run(generator)
        nodes = {name: func for name, func in self._nodes}
        edges = dict(self._edges)
        order = [name for name, _ in self._nodes]

        class CompiledGraph:
            def __init__(self, nodes, edges, order, state_cls):
                self.nodes = nodes
                self.edges = edges
                self.order = order
                self.state_cls = state_cls

            def iter_run(self, initial_state=None):
                state = initial_state or self.state_cls()
                idx = 0
                # Start from first node
                current = self.order[0] if self.order else None
                while current and current is not END:
                    node_fn = self.nodes[current]
                    state = node_fn(state)
                    yield state
                    nxt = self.edges.get(current)
                    if nxt is END:
                        break
                    current = nxt
                    idx += 1
                return state

        return CompiledGraph(nodes, edges, order, self.state_cls)
