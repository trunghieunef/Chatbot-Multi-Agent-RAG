# Synthesis: Forbid Self-Contradiction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the synthesized answer from both denying and providing data for the same topic, by hardening the synthesis prompt instructions.

**Architecture:** Prompt-only change to one function, `build_synthesis_prompt` in `agent_service/graph/synthesis.py`. Add two coherence/reconciliation instructions and rewrite the existing "if evidence is missing" line so it no longer invites hedging when data is present. No change to data fed to the LLM, agents, tools, `SynthesisPayload`, or grounding.

**Tech Stack:** Python 3.12, pytest. Agent tests run offline (fake LLM); this change is verified by a deterministic prompt-content test plus manual server check.

## Global Constraints

- Instruction strings stay in **English** (consistent with the existing system-prompt lines in `build_synthesis_prompt`); user-facing answer remains Vietnamese via the data.
- Do not change `build_synthesis_prompt`'s signature, the data passed in, or any other function.
- `python -m pytest agent_service/tests -q` must stay green.

---

### Task 1: Harden the synthesis prompt against self-contradiction

**Files:**
- Modify: `agent_service/graph/synthesis.py` (the instruction list inside `build_synthesis_prompt`)
- Test: `agent_service/tests/test_synthesis.py` (add one test)

**Interfaces:**
- Consumes: `build_synthesis_prompt(*, query: str, conversation_context: list[dict], agent_results: dict[str, dict], supervisor_plan: dict | None = None) -> str` (existing, unchanged signature).
- Produces: same function, with three changed instruction lines. No new exports.

- [ ] **Step 1: Write the failing test**

Add to `agent_service/tests/test_synthesis.py`:

```python
def test_synthesis_prompt_forbids_self_contradiction():
    from agent_service.graph.synthesis import build_synthesis_prompt

    prompt = build_synthesis_prompt(
        query="giá Nam Từ Liêm tăng hay giảm?",
        conversation_context=[],
        agent_results={},
        supervisor_plan=None,
    )

    # New coherence + reconciliation guidance is present.
    assert "Never contradict yourself" in prompt
    assert "Reconcile partial results" in prompt
    # The old standalone hedging line is gone (it invited "no data" + data).
    assert (
        "If evidence is missing, say what is missing and ask a useful follow-up."
        not in prompt
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest agent_service/tests/test_synthesis.py::test_synthesis_prompt_forbids_self_contradiction -q`
Expected: FAIL — the assertions for "Never contradict yourself" / "Reconcile partial results" fail (and the old line is still present).

- [ ] **Step 3: Edit the instruction list in `build_synthesis_prompt`**

In `agent_service/graph/synthesis.py`, inside the `return "\n".join([ ... ])` instruction list, replace this single line:

```python
            "If evidence is missing, say what is missing and ask a useful follow-up.",
```

with these three lines:

```python
            (
                "Produce ONE coherent answer. Never contradict yourself — if any "
                "agent output contains data for a topic (for example a price trend), "
                "present that data and do NOT also claim the data is missing or "
                "unavailable for that same topic."
            ),
            (
                "Reconcile partial results: when one agent returns data and another "
                "returns none for the same topic, use the data and omit any "
                "'no data' statement."
            ),
            (
                "Only state that information is missing when NO agent output contains "
                "it — never alongside data you are presenting; in that case ask a "
                "useful follow-up."
            ),
```

Leave every other instruction line, the f-strings (`User query`, `Conversation context`, `Agent results`, `Supervisor plan`), and the function signature unchanged.

- [ ] **Step 4: Run the new test + the synthesis suite**

Run: `python -m pytest agent_service/tests/test_synthesis.py -q`
Expected: PASS (new test passes; existing synthesis tests unaffected — the fake-LLM path returns a fixed payload regardless of prompt text).

- [ ] **Step 5: Run the full agent suite (regression)**

Run: `python -m pytest agent_service/tests -q`
Expected: same pass count as before plus the one new test (no regressions).

- [ ] **Step 6: Commit**

```bash
git add agent_service/graph/synthesis.py agent_service/tests/test_synthesis.py
git commit -m "fix: synthesis prompt forbids self-contradiction, reconciles partial results"
```

---

## Self-Review

**Spec coverage:**
- "Add coherence instruction" → Step 3 line 1 ✓
- "Add reconciliation instruction" → Step 3 line 2 ✓
- "Replace the missing-evidence line" → Step 3 line 3 (replaces the old line) ✓
- "Unit test asserts new guidance present + old line gone" → Step 1 ✓
- "Regression suite green" → Step 5 ✓
- Non-goals (city extraction, programmatic detector, context trimming) — not in any task ✓

**Placeholder scan:** none — exact instruction text and test code given.

**Type consistency:** `build_synthesis_prompt` signature is used identically in the test (Step 1) and unchanged in the edit (Step 3). Substrings asserted in the test ("Never contradict yourself", "Reconcile partial results") match the instruction text added in Step 3 verbatim.

## Manual verification (post-deploy, not a task gate)

After deploy (`docker compose up -d --build agent-service`), on the server re-ask
*"Giá chung cư ở Nam Từ Liêm gần đây tăng hay giảm?"* — the answer presents the
trend without also saying it lacks the trend. (LLM-behaviour effect is only
confirmable empirically.)
