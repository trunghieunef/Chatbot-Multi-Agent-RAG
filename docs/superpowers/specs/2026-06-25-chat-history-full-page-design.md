# Chat history on the full-page assistant (`/tro-ly-ai`) — Design

## Context

A user lost an in-progress conversation by navigating away: the chatbot keeps
messages and `sessionId` only in React state (`frontend/lib/useChat.ts`), so a
reload or route change resets them. The conversation itself **is** persisted
server-side (keyed by `session_id`), but the frontend forgets the id.

The full-page assistant `frontend/app/tro-ly-ai/page.tsx` (`useChat({ mode: "full" })`)
already renders a session-list sidebar (`sessions` / `selectSession` / `newSession`)
and works for **logged-in** users, because `GET /api/v1/chat/sessions` returns
their sessions. The gap: for **anonymous** users that endpoint returns `[]`
(`backend/app/routers/chat.py:790-792`), so the sidebar is empty — no history to
reopen or continue. The user who hit this was anonymous.

Goal: on the full page, an anonymous (or logged-in) user can see their past
conversations, click one to view its history, and continue chatting in it —
surviving reloads and navigation.

## Scope

- **Target:** the full page `/tro-ly-ai` only. The mini widget is out of scope.
- **No backend change.** Loading a single anonymous session by id already works:
  `GET /chat/sessions/{id}` only blocks cross-owner access for sessions that have
  a `user_id` (`session_guard.verify_session_ownership`); anonymous sessions have
  `user_id IS NULL`, so any client may load them by id.
- **Non-goals:** cross-device sync for anonymous users (localStorage is
  per-browser by nature), the mini widget, server-side anon identity.

## Approach

The full page already has the UI and the wiring (`selectSession`, `newSession`,
history load). The only missing piece is a **source for the session list when
anonymous**. We add a localStorage-backed conversation registry that mirrors the
shape the sidebar already consumes.

- **Logged-in:** keep using `getChatSessions()` (unchanged).
- **Anonymous:** read the list from a localStorage registry of conversations
  created on this browser.

## Components

### 1. `frontend/lib/chatHistory.ts` (new)
A small, self-contained localStorage helper. One responsibility: track the
anonymous conversation registry. Pure functions, SSR-safe (guard `typeof window`).

- Storage key: `chat:anon-sessions` → JSON array of
  `{ id: string; title: string; updatedAt: string }`.
- Storage key: `chat:last-session` → the id of the most recently active
  conversation (for restore-on-open).
- Exports:
  - `listConversations(): ChatHistoryEntry[]` (most-recent first)
  - `upsertConversation(id, title): void` (insert or refresh `updatedAt`; first
    write sets the title)
  - `removeConversation(id): void`
  - `getLastSessionId(): string | null` / `setLastSessionId(id): void`
- `title` = the first user message, trimmed to ~40 chars (caller supplies it;
  the helper does not inspect messages).

### 2. `frontend/lib/useChat.ts` (edit)
- On a successful send that returns `res.session_id`:
  - `setLastSessionId(res.session_id)`.
  - When anonymous, `upsertConversation(res.session_id, title)` where `title`
    is the first user message of the conversation (use the existing first user
    `Message`, fall back to a default like "Cuộc trò chuyện").
- `sessions` source: when logged-in, `getChatSessions()` (current behaviour);
  when anonymous, map the registry into the `ChatSessionResponse` shape the
  sidebar renders (id, title, updated_at, message_count optional). Auth state is
  derived the same way the rest of `lib/api.ts` does (presence of the stored
  token); reuse that check rather than adding a new one.
- `selectSession(id)`: drop the `if (!isFull) return` guard's logged-in-only
  assumption only as needed; it already calls `getChatSessionHistory(id)` and
  sets `sessionId`, so continuing a conversation appends to that session.
- On `useChat` mount in full mode: if `getLastSessionId()` returns an id, restore
  it (set `sessionId` + load its history via the existing select path). Failures
  (deleted/expired session → 404) fall back to a fresh conversation and the
  stale registry entry is removed.
- `newSession`: clear current `sessionId`/messages; the next first message
  registers a new entry.

### 3. No changes to the mini widget or backend.

## Data flow

```
anon sends msg ──► backend creates session, returns session_id
   │                         │
   │   upsertConversation(id, firstUserMsg)  + setLastSessionId(id)   [localStorage]
   ▼
sidebar list (anon) ◄── listConversations()         click ──► selectSession(id)
                                                                 │
                                          getChatSessionHistory(id) ─► render messages
                                                                 │
                                   next send uses sessionId=id ─► backend appends
reload /tro-ly-ai ──► getLastSessionId() ─► restore + load history
```

## Error handling / edge cases

- **SSR / no window:** all localStorage access guarded; helpers return empty/null.
- **Stale id (404 on history load):** remove from registry, start fresh, no crash.
- **Corrupt JSON in localStorage:** parse defensively; on error treat as empty.
- **Logged-in user with prior anon registry:** logged-in path uses the backend
  list, so anon registry entries simply aren't shown while logged in (acceptable).
- **Registry growth:** cap to the most recent N (e.g. 30) conversations to bound
  localStorage size.

## Testing

- `cd frontend && npm run lint` (no new issues) + `npx tsc --noEmit` (clean).
- Manual, anonymous, on `/tro-ly-ai`:
  1. Chat a few turns → reload → conversation still present in the sidebar and
     restored in the panel.
  2. Start a second conversation ("Trò chuyện mới") → both appear in the sidebar.
  3. Click the older conversation → its history renders → send a message → it
     continues that same conversation (verify the new turn persists after reload).
- Manual, logged-in: sidebar still uses the backend session list and behaves as
  before (regression check).

## Out of scope / follow-ups

- Mini-widget history restore (separate, if wanted later).
- Server-side anonymous identity (cookie/device id) for cross-device anon sync.
- The earlier-noted synthesis contradiction fix (ROI "computed vs cannot
  compute") — tracked separately.
