# Chat History on the Full-Page Assistant — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On `/tro-ly-ai`, anonymous users can see, reopen, and continue past conversations (surviving reload/navigation); logged-in users keep using the backend session list.

**Architecture:** Frontend-only. The full page already renders a session sidebar wired to `selectSession`/`newSession`; the only gap is that `GET /chat/sessions` returns `[]` for anonymous users. Add a localStorage "conversation registry" that feeds the sidebar when anonymous, and persist/restore the active session id. Loading a single anon session by id already works server-side (no ownership block when `user_id IS NULL`).

**Tech Stack:** Next.js App Router, React 19, TypeScript strict, Tailwind v4. No frontend test runner exists in this repo — the per-task gate is `npm run lint` + `npx tsc --noEmit` + a scripted manual check, consistent with how frontend work is verified here.

## Global Constraints

- TypeScript strict mode; functional components + hooks only.
- All localStorage access MUST be SSR-safe (`typeof window === "undefined"` guard) — `useChat`/its libs run during Next SSR.
- Auth detection MUST reuse the existing convention: logged-in ⇔ `localStorage.getItem("token")` is truthy (see `frontend/lib/api.ts:45-48`).
- No backend changes. No mini-widget (`ChatWidget.tsx`) changes.
- UI/comment language: Vietnamese for user-facing text, English for code/comments.

---

### Task 1: Conversation registry module (`lib/chatHistory.ts`)

**Files:**
- Create: `frontend/lib/chatHistory.ts`

**Interfaces:**
- Consumes: `ChatSessionResponse` from `@/lib/types` (fields: `id: string`, `title: string | null`, `message_count: number`, `created_at`/`updated_at: string | null` — confirm exact fields at `frontend/lib/types.ts:216-222`).
- Produces:
  - `interface ChatHistoryEntry { id: string; title: string; updatedAt: string }`
  - `listConversations(): ChatHistoryEntry[]` (most-recent first)
  - `upsertConversation(id: string, title: string): void` (insert with title on first write; later writes only bump `updatedAt`)
  - `removeConversation(id: string): void`
  - `getLastSessionId(): string | null`
  - `setLastSessionId(id: string): void`
  - `registryAsSessions(): ChatSessionResponse[]` (registry mapped into the sidebar's shape)

- [ ] **Step 1: Create the module with the full implementation**

```typescript
// frontend/lib/chatHistory.ts
// Per-browser registry of anonymous chat conversations, persisted in localStorage.
// Anonymous users get [] from GET /chat/sessions, so the full-page sidebar is fed
// from this registry instead. SSR-safe: every access guards `window`.
import type { ChatSessionResponse } from "@/lib/types";

const REGISTRY_KEY = "chat:anon-sessions";
const LAST_SESSION_KEY = "chat:last-session";
const MAX_ENTRIES = 30;
const TITLE_MAX = 40;

export interface ChatHistoryEntry {
  id: string;
  title: string;
  updatedAt: string;
}

function readRegistry(): ChatHistoryEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(REGISTRY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as ChatHistoryEntry[]) : [];
  } catch {
    return [];
  }
}

function writeRegistry(entries: ChatHistoryEntry[]): void {
  if (typeof window === "undefined") return;
  try {
    const trimmed = [...entries]
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .slice(0, MAX_ENTRIES);
    window.localStorage.setItem(REGISTRY_KEY, JSON.stringify(trimmed));
  } catch {
    // ignore quota / disabled storage
  }
}

export function listConversations(): ChatHistoryEntry[] {
  return readRegistry().sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export function upsertConversation(id: string, title: string): void {
  const entries = readRegistry();
  const now = new Date().toISOString();
  const existing = entries.find((e) => e.id === id);
  if (existing) {
    existing.updatedAt = now; // keep the original title
  } else {
    const clean = title.trim().slice(0, TITLE_MAX) || "Cuộc trò chuyện";
    entries.push({ id, title: clean, updatedAt: now });
  }
  writeRegistry(entries);
}

export function removeConversation(id: string): void {
  writeRegistry(readRegistry().filter((e) => e.id !== id));
}

export function getLastSessionId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(LAST_SESSION_KEY);
  } catch {
    return null;
  }
}

export function setLastSessionId(id: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LAST_SESSION_KEY, id);
  } catch {
    // ignore
  }
}

// Map registry entries into the shape the session sidebar already renders.
// Verify the exact ChatSessionResponse fields at frontend/lib/types.ts:216-222
// and fill any additional required field sensibly (use updatedAt for dates).
export function registryAsSessions(): ChatSessionResponse[] {
  return listConversations().map((e) => ({
    id: e.id,
    title: e.title,
    message_count: 0,
    created_at: e.updatedAt,
    updated_at: e.updatedAt,
  }));
}
```

- [ ] **Step 2: Lint + typecheck**

Run: `cd frontend && npm run lint && npx tsc --noEmit 2>&1 | grep -i chatHistory || echo "no chatHistory type errors"`
Expected: no new lint errors; no `chatHistory.ts` type errors. If `registryAsSessions` complains about a missing required field, add it per the actual `ChatSessionResponse` interface.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/chatHistory.ts
git commit -m "feat: localStorage registry for anonymous chat conversations"
```

---

### Task 2: Wire the registry into `useChat` (full-page history for anon)

**Files:**
- Modify: `frontend/lib/useChat.ts` (`loadSessions` ~76-87; the `useEffect` ~89-93; `send` success path where `setSessionId(res.session_id)` is called ~119; `selectSession` ~157-185 incl. its `catch`; `newSession` unchanged)

**Interfaces:**
- Consumes from Task 1: `listConversations`, `upsertConversation`, `removeConversation`, `getLastSessionId`, `setLastSessionId`, `registryAsSessions`.
- Produces: no new exports; existing `sessions` / `selectSession` / `newSession` now also work for anonymous users in full mode.

- [ ] **Step 1: Import the registry helpers**

Add to the imports at the top of `frontend/lib/useChat.ts`:

```typescript
import {
  registryAsSessions,
  upsertConversation,
  removeConversation,
  getLastSessionId,
  setLastSessionId,
} from "@/lib/chatHistory";
```

- [ ] **Step 2: Feed the sidebar from the registry when anonymous**

Replace the body of `loadSessions` (currently `getChatSessions()` → `setSessions`, anon silently fails to `[]`):

```typescript
  const loadSessions = useCallback(async () => {
    if (!isFull) return;
    setLoadingSessions(true);
    try {
      if (localStorage.getItem("token")) {
        const data = await getChatSessions();
        setSessions(data);
      } else {
        setSessions(registryAsSessions()); // anonymous: from localStorage registry
      }
    } catch {
      setSessions(registryAsSessions()); // fallback to local registry
    } finally {
      setLoadingSessions(false);
    }
  }, [isFull]);
```

- [ ] **Step 3: Register the session + persist last id on a successful send**

In `send`, immediately after `setSessionId(res.session_id);`, add:

```typescript
        setLastSessionId(res.session_id);
        if (!localStorage.getItem("token")) {
          // First user message becomes the conversation title; later sends only
          // refresh updatedAt (upsert keeps the original title).
          upsertConversation(res.session_id, msg);
          if (isFull) loadSessions();
        }
```

(`msg` is the message text already resolved at the top of `send`; `isFull`/`loadSessions` are in scope. Add `loadSessions` to the `send` `useCallback` dependency array.)

- [ ] **Step 4: Restore the last conversation when the full page mounts**

Replace the mount effect (currently `if (isFull) loadSessions();`):

```typescript
  useEffect(() => {
    if (!isFull) return;
    loadSessions();
    const last = getLastSessionId();
    if (last) {
      selectSession(last); // restores messages + sets sessionId so chat continues it
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isFull]);
```

This effect must be placed AFTER `selectSession` is defined (move it below `selectSession`, or keep `selectSession` defined above it). If ordering forces a change, define `selectSession` before this effect.

- [ ] **Step 5: Drop stale conversations on a failed history load**

In `selectSession`'s `catch` block (the load of `getChatSessionHistory(id)` can 404 if the session was deleted/expired), replace the empty/partial catch with:

```typescript
      } catch {
        removeConversation(id); // stale id — drop it and start fresh
        newSession();
      }
```

(`newSession` is defined in this hook; if it is declared after `selectSession`, reference it via the existing pattern already used in `deleteSession`/the file — confirm `newSession` is in scope, otherwise hoist its definition above `selectSession`.)

- [ ] **Step 6: Lint + typecheck**

Run: `cd frontend && npm run lint && npx tsc --noEmit 2>&1 | grep -iE "useChat|chatHistory" || echo "no type errors in changed files"`
Expected: no new lint errors (watch for `react-hooks/exhaustive-deps` — the disable comment in Step 4 handles the intentional one); no type errors in `useChat.ts`.

- [ ] **Step 7: Manual verification (anonymous), then commit**

Start the app (`cd frontend && npm run dev`) OR rely on the deployed build. As an anonymous user (no `token` in localStorage), on `/tro-ly-ai`:
1. Send 2–3 messages → reload the page → the conversation appears in the sidebar AND its messages are restored in the panel.
2. Click "Trò chuyện mới", send a message → both conversations now appear in the sidebar.
3. Click the older conversation → its history renders → send another message → it continues that same conversation; reload → the new turn is still there.
4. Regression (logged-in): with a `token` set, the sidebar still loads from the backend (`getChatSessions`) and behaves as before.

```bash
git add frontend/lib/useChat.ts
git commit -m "feat: full-page chat history + continue for anonymous users"
```

---

## Self-Review

**Spec coverage:**
- Anon session list (backend returns []) → Task 1 registry + Task 2 Step 2 ✓
- Register session on creation (title = first user msg) → Task 2 Step 3 ✓
- View history of an old conversation → existing `selectSession` + Task 2 (now reachable for anon) ✓
- Continue chatting in a selected conversation → `selectSession` sets `sessionId`; subsequent `send` uses it ✓
- Restore last conversation on reload → Task 2 Step 4 ✓
- Logged-in path unchanged → Task 2 Step 2 (token branch) ✓
- Edge: stale id 404 → Task 2 Step 5 ✓; SSR-safe → Task 1 guards ✓; corrupt JSON → `readRegistry` try/catch ✓; registry cap 30 → `writeRegistry` slice ✓
- Mini widget / backend untouched → no tasks touch them ✓

**Placeholder scan:** none — all steps carry concrete code/commands.

**Type consistency:** `registryAsSessions(): ChatSessionResponse[]` is consumed by `setSessions` (same type the sidebar renders). `ChatHistoryEntry` defined once in Task 1, used internally. Helper names match between Task 1 (exports) and Task 2 (imports): `registryAsSessions`, `upsertConversation`, `removeConversation`, `getLastSessionId`, `setLastSessionId`.
