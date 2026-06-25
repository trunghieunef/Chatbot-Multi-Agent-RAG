# Synthesis: forbid self-contradiction — Design

## Context

The final synthesize step (`agent_service/graph/synthesis.py` → `synthesize_final_answer`,
which calls an LLM via `build_synthesis_prompt`) merges every specialist agent's
output into one Vietnamese answer. When one agent returns data for a topic and
another returns nothing for the same topic, the LLM has repeatedly produced
**self-contradictory** answers — e.g. for "giá Nam Từ Liêm tăng hay giảm?" it wrote
*"Hiện tại, tôi không có thông tin … tăng hay giảm"* and, in the same message,
*"Dựa trên dữ liệu … giá có xu hướng tăng giảm không đều"* with four months of real
figures. The same shape appeared earlier (ROI "computed 2.51%" vs "cannot compute
ROI"; "tìm thấy 5 căn" vs "không tìm thấy căn nào").

Root cause: the synthesis prompt has no instruction to be internally consistent,
and its existing line *"If evidence is missing, say what is missing and ask a
follow-up"* actively invites the LLM to hedge ("I don't have data") even when
another agent supplied the data, then it appends the data anyway.

Goal: the synthesized answer must never both deny and provide data for the same
topic. When any agent output contains the data, present it; only state something
is missing when no agent output contains it.

## Scope

- **Change one function:** `build_synthesis_prompt` in `agent_service/graph/synthesis.py`
  — prompt instructions only.
- **No change** to what data is fed to the LLM (all agent results stay visible),
  to specialist agents/tools, to `SynthesisPayload`, or to the grounding logic.
- **Non-goals:** programmatic NL contradiction detection; the separate `city`
  extraction gap (metrics returns empty without city) — tracked separately;
  conversation-context trimming.

## Approach

Harden the instruction list returned by `build_synthesis_prompt`:

1. **Add (coherence):** "Produce ONE coherent answer. Never contradict yourself —
   if any agent output contains data for a topic (for example a price trend),
   present that data and do NOT also claim the data is missing or unavailable for
   that same topic."
2. **Add (reconciliation):** "Reconcile partial results: when one agent returns
   data and another returns none for the same topic, use the data and omit any
   'no data' statement."
3. **Replace the existing line** "If evidence is missing, say what is missing and
   ask a useful follow-up." with: "Only state that information is missing when NO
   agent output contains it — never alongside data you are presenting; in that
   case ask a useful follow-up."

Instructions stay in English, consistent with the rest of this system prompt
(the user-facing answer remains Vietnamese, driven by the data and the existing
"Vietnamese real-estate assistant" framing).

## Components

`agent_service/graph/synthesis.py` → `build_synthesis_prompt`: the only unit
touched. It takes the query, conversation context, agent results, and supervisor
plan and returns a prompt string; this change edits three lines of that string's
instruction list. No interface or signature change.

## Testing

- **Unit (deterministic, no LLM):** call `build_synthesis_prompt(query=..., conversation_context=[], agent_results={}, supervisor_plan=None)` and assert the returned string contains the new guidance (e.g. substrings "Never contradict yourself" and "Reconcile partial results") and no longer contains the old standalone "If evidence is missing, say what is missing and ask a useful follow-up." line.
- **Regression:** `python -m pytest agent_service/tests -q` stays green (the fake-LLM synthesis path in `test_synthesis.py` is unaffected — it returns a fixed payload regardless of prompt text).
- **Manual (the real check):** on the server, re-ask *"Giá chung cư ở Nam Từ Liêm gần đây tăng hay giảm?"* and the combined *"Tìm căn hộ 2PN Nam Từ Liêm dưới 5 tỷ và giá khu vực tăng hay giảm?"* — the answer presents the trend without also saying it lacks the trend. The LLM-behaviour effect can only be confirmed empirically; the unit test only guarantees the guidance is present.

## Out of scope / follow-ups

- Router `city` extraction so `lookup_market_metrics` ("current avg price") also
  returns data — reduces one trigger for the hedge, separate change.
- Any programmatic post-hoc contradiction detector.
