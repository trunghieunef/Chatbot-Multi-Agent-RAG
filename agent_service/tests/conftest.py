from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for path in (ROOT, BACKEND):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# Test files that import a removed agent architecture
# (graph.workflow / graph.nodes / graph.react_controller / graph.retrieval_planner).
# Quarantined here so the suite collects; triage/delete in a later cleanup.
collect_ignore = [
    "test_agentic_e2e.py",
    "test_blackboard_specialists.py",
    "test_collaborative_investment_graph.py",
    "test_conversation_context.py",
    "test_graph_smoke.py",
    "test_investment_calculators.py",
    "test_investment_model_node.py",
    "test_investment_safety.py",
    "test_investment_trace.py",
    "test_memory_node.py",
    "test_react_loop.py",
    "test_retrieval_parallel.py",
    "test_specialists_parallel.py",
]
