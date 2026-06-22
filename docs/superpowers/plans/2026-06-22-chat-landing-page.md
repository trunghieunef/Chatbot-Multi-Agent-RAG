# Chatbot Landing Page — `/tro-ly-ai` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a ChatGPT-style chatbot landing page at `/tro-ly-ai` with session history sidebar, full-page chat, and session CRUD. Reuse chat logic via shared `useChat` hook.

**Architecture:** Hybrid approach — extract `useChat` hook from `ChatWidget`, build `ChatSidebar` + `ChatPanel` for full-page mode, keep `ChatWidget` in mini mode on all pages. Backend gets DELETE + PATCH `/chat/sessions/{id}`.

**Tech Stack:** Next.js 14 App Router, React 19, Tailwind CSS v4, TypeScript, FastAPI, SQLAlchemy async, PostgreSQL

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| MODIFY | `backend/app/schemas/chat.py` | Add `ChatSessionUpdate` schema |
| MODIFY | `backend/app/routers/chat.py` | Add DELETE + PATCH endpoints |
| MODIFY | `frontend/lib/api.ts` | Add `getSessions`, `getSessionHistory`, `deleteSession`, `renameSession` |
| MODIFY | `frontend/lib/types.ts` | Ensure `ChatSessionResponse` exported (already exists, verify) |
| CREATE | `frontend/lib/useChat.ts` | Shared chat hook |
| MODIFY | `frontend/components/chatbot/ChatWidget.tsx` | Use `useChat("mini")`, add expand button |
| CREATE | `frontend/components/chatbot/ChatSidebar.tsx` | Session list sidebar |
| CREATE | `frontend/components/chatbot/ChatPanel.tsx` | Full-page chat panel |
| CREATE | `frontend/app/tro-ly-ai/page.tsx` | Landing page (combines sidebar + panel) |

---

### Task 1: Backend — `ChatSessionUpdate` schema

**Files:**
- Modify: `backend/app/schemas/chat.py`

- [ ] **Step 1: Add rename schema**

Add after `ChatHistoryResponse` class (end of file):

```python
class ChatSessionUpdate(BaseModel):
    """Request to update a chat session."""
    title: str = Field(..., min_length=1, max_length=300)
```

- [ ] **Step 2: Verify syntax**

Run: `python -m compileall backend\app\schemas\chat.py`
Expected: Compilation successful, no errors.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/chat.py
git commit -m "feat: add ChatSessionUpdate schema for rename"
```

---

### Task 2: Backend — DELETE `/chat/sessions/{session_id}`

**Files:**
- Modify: `backend/app/routers/chat.py`

- [ ] **Step 1: Add DELETE endpoint**

Add after the `get_session_history` endpoint (after line ~870). Insert before any `@router` that follows:

```python
@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a chat session and all its messages. Must be session owner."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    verify_session_ownership(session, user)

    # Cascade delete messages first, then session
    await db.execute(
        ChatMessage.__table__.delete().where(ChatMessage.session_id == session_id)
    )
    await db.delete(session)
    await db.commit()
```

- [ ] **Step 2: Verify syntax**

Run: `python -m compileall backend\app\routers\chat.py`
Expected: Compilation successful.

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/chat.py
git commit -m "feat: add DELETE /chat/sessions/{id} endpoint"
```

---

### Task 3: Backend — PATCH `/chat/sessions/{session_id}` (rename)

**Files:**
- Modify: `backend/app/routers/chat.py`

- [ ] **Step 1: Add PATCH endpoint**

Add after the DELETE endpoint:

```python
@router.patch(
    "/sessions/{session_id}",
    response_model=ChatSessionResponse,
)
async def rename_session(
    session_id: uuid.UUID,
    body: ChatSessionUpdate,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Rename a chat session. Must be session owner."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    verify_session_ownership(session, user)

    session.title = body.title
    await db.commit()
    await db.refresh(session)

    # Count messages
    count_q = await db.execute(
        select(func.count())
        .select_from(ChatMessage)
        .where(ChatMessage.session_id == session_id)
    )
    msg_count = count_q.scalar() or 0

    return ChatSessionResponse(
        id=session.id,
        title=session.title,
        message_count=msg_count,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )
```

- [ ] **Step 2: Add import for ChatSessionUpdate**

Update the import line at top of file (around line 28-35) to include `ChatSessionUpdate`:

```python
from app.schemas.chat import (
    ChatFeedbackRequest,
    ChatFeedbackResponse,
    ChatHistoryResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSessionResponse,
    ChatSessionUpdate,
)
```

- [ ] **Step 3: Verify syntax**

Run: `python -m compileall backend\app\routers\chat.py`
Expected: Compilation successful.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/chat.py
git commit -m "feat: add PATCH /chat/sessions/{id} for rename"
```

---

### Task 4: Frontend — API client additions

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/types.ts` (verify, may not need changes)

- [ ] **Step 1: Add chat session API functions**

Add after the `sendChatFeedback` function (before the `/* Admin */` section):

```typescript
/* Chat sessions */

export async function getChatSessions(): Promise<ChatSessionResponse[]> {
  return fetchJSON(`${BASE}/chat/sessions`, {
    headers: authHeaders(),
  });
}

export async function getChatSessionHistory(
  sessionId: string
): Promise<ChatHistoryResponse> {
  return fetchJSON(`${BASE}/chat/sessions/${sessionId}`, {
    headers: authHeaders(),
  });
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  await fetch(`${BASE}/chat/sessions/${sessionId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
}

export async function renameChatSession(
  sessionId: string,
  title: string
): Promise<ChatSessionResponse> {
  return fetchJSON(`${BASE}/chat/sessions/${sessionId}`, {
    method: "PATCH",
    headers: authHeaders(),
    body: JSON.stringify({ title }),
  });
}
```

- [ ] **Step 2: Verify imports in types.ts**

Run: `grep "ChatSessionResponse\|ChatHistoryResponse" frontend/lib/types.ts`
Expected: Both types exist. If `ChatHistoryResponse` is missing, add:

```typescript
export interface ChatSessionResponse {
  id: string;
  title: string | null;
  message_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface ChatHistoryResponse {
  session: ChatSessionResponse;
  messages: ChatMessageResponse[];
}
```

- [ ] **Step 3: Verify lint**

Run: `cd frontend && npm run lint`
Expected: No new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts frontend/lib/types.ts
git commit -m "feat: add chat session API functions (list, history, delete, rename)"
```

---

### Task 5: Frontend — `useChat` hook

**Files:**
- Create: `frontend/lib/useChat.ts`

- [ ] **Step 1: Create the hook file**

```typescript
"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import {
  sendChatMessage,
  getChatSessions,
  getChatSessionHistory,
  deleteChatSession,
  renameChatSession,
} from "@/lib/api";
import type {
  ChatMessageResponse,
  ChatSessionResponse,
  ChatSource,
  MemoryHint,
} from "@/lib/types";

export interface Message {
  role: "user" | "assistant";
  content: string;
  agent_used?: string | null;
  agents_used?: string[] | null;
  sources?: ChatSource[] | null;
  suggested_actions?: string[] | null;
  trace_summary?: ChatMessageResponse["trace_summary"];
  memory_hints?: ChatMessageResponse["memory_hints"];
  feedback_id?: string | null;
  request_id?: string | null;
}

export type ChatMode = "mini" | "full";

interface UseChatOptions {
  mode: ChatMode;
}

export function useChat(options: UseChatOptions = { mode: "mini" }) {
  const { mode } = options;
  const isFull = mode === "full";

  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Xin chào! Tôi là trợ lý AI tư vấn bất động sản. Bạn muốn tìm kiếm nhà đất, hỏi về thị trường, hay cần tư vấn pháp lý?",
      suggested_actions: [
        "Tìm căn hộ 2PN Quận 7",
        "Xu hướng giá nhà 2024",
        "Thủ tục mua nhà lần đầu",
      ],
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);

  // Full-mode state
  const [sessions, setSessions] = useState<ChatSessionResponse[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  // Load sessions in full mode
  const loadSessions = useCallback(async () => {
    if (!isFull) return;
    setLoadingSessions(true);
    try {
      const data = await getChatSessions();
      setSessions(data);
    } catch {
      // Silently fail — user may be anonymous
    } finally {
      setLoadingSessions(false);
    }
  }, [isFull]);

  useEffect(() => {
    if (isFull) {
      loadSessions();
    }
  }, [isFull, loadSessions]);

  // Send message
  const send = useCallback(
    async (text?: string) => {
      const msg = text || input.trim();
      if (!msg || loading) return;

      setInput("");
      setMessages((prev) => [...prev, { role: "user", content: msg }]);
      setLoading(true);

      try {
        const res: ChatMessageResponse = await sendChatMessage({
          message: msg,
          session_id: sessionId || undefined,
        });
        setSessionId(res.session_id);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: res.content,
            agent_used: res.agent_used,
            agents_used: res.agents_used,
            sources: res.sources,
            suggested_actions: res.suggested_actions,
            trace_summary: res.trace_summary,
            memory_hints: res.memory_hints,
            feedback_id: res.feedback_id,
            request_id: res.request_id,
          },
        ]);
        // Refresh session list in full mode
        if (isFull && !sessionId) {
          loadSessions();
        }
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content:
              "Xin lỗi, đã có lỗi xảy ra. Backend có thể chưa khởi động. Vui lòng thử lại.",
          },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [input, loading, sessionId, isFull, loadSessions]
  );

  // Select a session and load its history
  const selectSession = useCallback(
    async (id: string) => {
      if (!isFull) return;
      setSessionId(id);
      setMessages([]);
      setLoading(true);
      try {
        const data = await getChatSessionHistory(id);
        setMessages(
          data.messages.map((m) => ({
            role: m.role as "user" | "assistant",
            content: m.content,
            agent_used: m.agent_used,
            agents_used: m.agents_used,
            sources: m.sources,
            suggested_actions: m.suggested_actions,
            trace_summary: m.trace_summary,
            memory_hints: m.memory_hints,
            feedback_id: m.feedback_id,
            request_id: m.request_id,
          }))
        );
      } catch {
        setMessages([
          {
            role: "assistant",
            content: "Không thể tải lịch sử. Vui lòng thử lại.",
          },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [isFull]
  );

  // Delete a session
  const deleteSession = useCallback(
    async (id: string) => {
      try {
        await deleteChatSession(id);
        setSessions((prev) => prev.filter((s) => s.id !== id));
        if (sessionId === id) {
          newSession();
        }
      } catch {
        // Silently fail
      }
    },
    [sessionId]
  );

  // Rename a session
  const renameSession = useCallback(
    async (id: string, title: string) => {
      try {
        const updated = await renameChatSession(id, title);
        setSessions((prev) =>
          prev.map((s) => (s.id === id ? updated : s))
        );
      } catch {
        // Silently fail
      }
    },
    []
  );

  // Create new session
  const newSession = useCallback(() => {
    setSessionId(null);
    setMessages([
      {
        role: "assistant",
        content:
          "Xin chào! Tôi là trợ lý AI tư vấn bất động sản. Bạn muốn tìm kiếm nhà đất, hỏi về thị trường, hay cần tư vấn pháp lý?",
        suggested_actions: [
          "Tìm căn hộ 2PN Quận 7",
          "Xu hướng giá nhà 2024",
          "Thủ tục mua nhà lần đầu",
        ],
      },
    ]);
  }, []);

  return {
    // State
    messages,
    input,
    loading,
    sessionId,
    sessions,
    loadingSessions,
    scrollRef,

    // Actions
    setInput,
    send,
    selectSession,
    deleteSession,
    renameSession,
    newSession,
    loadSessions,
  };
}
```

- [ ] **Step 2: Verify lint**

Run: `cd frontend && npm run lint`
Expected: No new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/useChat.ts
git commit -m "feat: add useChat hook shared between widget and landing page"
```

---

### Task 6: Frontend — Refactor ChatWidget to use `useChat`

**Files:**
- Modify: `frontend/components/chatbot/ChatWidget.tsx`

- [ ] **Step 1: Update ChatWidget to use useChat("mini")**

Replace the entire component file. The key changes are:
- Import `useChat` instead of inline state management
- Pass `mode: "mini"` 
- Keep all the UI rendering (bubbles, sources, memory hints) — same JSX
- Add `Maximize2` and `useRouter` for expand button (already done in earlier edit)

Read the current file and rewrite using `useChat`:

```typescript
"use client";

import { BarChart3, FileText, Home, MapPin, Maximize2, MessageCircle, Scale, Send, Bot, TrendingUp, User, Sparkles, X } from "lucide-react";
import { useChat } from "@/lib/useChat";
import { useRouter } from "next/navigation";
import { getListingSourceDetails, getMarketSourceSummary, getSourceKind, getSourceTitle } from "@/lib/chatSourceDisplay";
import type { ChatSource, MemoryHint, StructuredWarning } from "@/lib/types";

export default function ChatWidget() {
  const router = useRouter();
  const {
    messages,
    input,
    loading,
    scrollRef,
    setInput,
    send,
  } = useChat({ mode: "mini" });

  const [open, setOpen] = useState(false);

  // ... rest of component is identical to current ChatWidget
  // (agentLabels, getAgentLabels, formatMemoryValue, etc.)
  // but uses send/setInput from useChat instead of local state
```

**IMPORTANT**: The complete replacement is too large to inline. Instead, make these targeted edits to the current `ChatWidget.tsx`:

1. Remove: `import { sendChatMessage } from "@/lib/api";`
2. Add: `import { useChat } from "@/lib/useChat";`
3. Remove: all state declarations (`const [messages, setMessages]`, `const [input, setInput]`, `const [loading, setLoading]`, `const [sessionId, setSessionId]`)
4. Remove: `const scrollRef = useRef<HTMLDivElement>(null);`
5. Remove: the `useEffect` that scrolls
6. Remove: the `handleSend` function
7. Add: `const { messages, input, loading, scrollRef, setInput, send } = useChat({ mode: "mini" });`
8. Rename: all `handleSend` calls → `send`
9. The rest of the component (agentLabels, getAgentLabels, formatMemoryValue, JSX) stays the same

- [ ] **Step 2: Verify lint**

Run: `cd frontend && npm run lint`
Expected: No new errors (may have unused import warnings, clean those up).

- [ ] **Step 3: Commit**

```bash
git add frontend/components/chatbot/ChatWidget.tsx
git commit -m "refactor: ChatWidget uses shared useChat hook"
```

---

### Task 7: Frontend — `ChatSidebar` component

**Files:**
- Create: `frontend/components/chatbot/ChatSidebar.tsx`

- [ ] **Step 1: Create the sidebar component**

```typescript
"use client";

import { useState } from "react";
import { MessageSquare, Plus, Pencil, Trash2, Search, X, Check } from "lucide-react";
import type { ChatSessionResponse } from "@/lib/types";

interface ChatSidebarProps {
  sessions: ChatSessionResponse[];
  currentSessionId: string | null;
  loading: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onNew: () => void;
}

export default function ChatSidebar({
  sessions,
  currentSessionId,
  loading,
  onSelect,
  onDelete,
  onRename,
  onNew,
}: ChatSidebarProps) {
  const [search, setSearch] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const filtered = sessions.filter((s) =>
    (s.title || "Cuộc trò chuyện mới")
      .toLowerCase()
      .includes(search.toLowerCase())
  );

  const timeAgo = (dateStr: string | null) => {
    if (!dateStr) return "";
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins} phút`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours} giờ`;
    const days = Math.floor(hours / 24);
    return `${days} ngày`;
  };

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-border bg-card">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-3 border-b border-border">
        <span className="text-sm font-semibold">Lịch sử chat</span>
        <button
          onClick={onNew}
          className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-colors hover:bg-primary-hover"
          title="Cuộc trò chuyện mới"
        >
          <Plus size={16} />
        </button>
      </div>

      {/* Search */}
      <div className="px-3 py-2">
        <div className="relative">
          <Search
            size={14}
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Tìm cuộc trò chuyện..."
            className="w-full rounded-lg border border-border bg-muted py-1.5 pl-8 pr-2 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-primary"
          />
        </div>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="space-y-1 px-2 py-2">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-10 animate-pulse rounded-lg bg-muted"
              />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-3 py-8 text-center text-xs text-muted-foreground">
            {search
              ? "Không tìm thấy"
              : "Chưa có cuộc trò chuyện nào"}
          </div>
        ) : (
          <div className="space-y-0.5 px-2 py-2">
            {filtered.map((s) => (
              <div
                key={s.id}
                className={`group flex items-center gap-2 rounded-lg px-2 py-2 cursor-pointer transition-colors ${
                  s.id === currentSessionId
                    ? "bg-primary/10 text-primary"
                    : "hover:bg-muted text-foreground"
                }`}
                onClick={() => onSelect(s.id)}
              >
                <MessageSquare size={14} className="shrink-0" />
                <div className="min-w-0 flex-1">
                  {editingId === s.id ? (
                    <div className="flex items-center gap-1">
                      <input
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        className="flex-1 rounded border border-border bg-card px-1 py-0.5 text-xs outline-none focus:border-primary"
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            onRename(s.id, editTitle || s.title || "Untitled");
                            setEditingId(null);
                          }
                          if (e.key === "Escape") setEditingId(null);
                        }}
                        onClick={(e) => e.stopPropagation()}
                      />
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onRename(s.id, editTitle || s.title || "Untitled");
                          setEditingId(null);
                        }}
                        className="rounded p-0.5 hover:bg-primary/20"
                      >
                        <Check size={12} />
                      </button>
                    </div>
                  ) : (
                    <>
                      <p className="truncate text-xs font-medium">
                        {s.title || "Cuộc trò chuyện mới"}
                      </p>
                      <p className="truncate text-[10px] text-muted-foreground">
                        {s.message_count} tin · {timeAgo(s.updated_at)}
                      </p>
                    </>
                  )}
                </div>
                {/* Hover actions */}
                <div className="hidden group-hover:flex items-center gap-0.5">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditingId(s.id);
                      setEditTitle(s.title || "");
                    }}
                    className="rounded p-1 hover:bg-muted-foreground/20"
                    title="Đổi tên"
                  >
                    <Pencil size={12} />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm("Xóa cuộc trò chuyện này?")) {
                        onDelete(s.id);
                      }
                    }}
                    className="rounded p-1 hover:bg-destructive/20 text-muted-foreground hover:text-destructive"
                    title="Xóa"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Verify lint**

Run: `cd frontend && npm run lint`
Expected: No new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/chatbot/ChatSidebar.tsx
git commit -m "feat: add ChatSidebar for session history"
```

---

### Task 8: Frontend — `ChatPanel` component

**Files:**
- Create: `frontend/components/chatbot/ChatPanel.tsx`

- [ ] **Step 1: Create the full-page chat panel**

This is the main chat area for `/tro-ly-ai`. It reuses the message rendering logic from ChatWidget but in a full-page layout.

```typescript
"use client";

import {
  BarChart3,
  FileText,
  Home,
  MapPin,
  Scale,
  Send,
  Bot,
  TrendingUp,
  User,
  Sparkles,
} from "lucide-react";
import { getListingSourceDetails, getMarketSourceSummary, getSourceKind, getSourceTitle } from "@/lib/chatSourceDisplay";
import type { ChatSource, MemoryHint } from "@/lib/types";
import type { Message } from "@/lib/useChat";

interface ChatPanelProps {
  messages: Message[];
  input: string;
  loading: boolean;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  onInputChange: (v: string) => void;
  onSend: (text?: string) => void;
  hasSession: boolean;
}

export default function ChatPanel({
  messages,
  input,
  loading,
  scrollRef,
  onInputChange,
  onSend,
  hasSession,
}: ChatPanelProps) {
  const agentLabels: Record<string, string> = {
    property_search: "Tìm kiếm",
    market_analysis: "Thị trường",
    legal_advisor: "Pháp lý",
    investment_advisor: "Đầu tư",
    simple_rag: "RAG",
    placeholder: "AI",
  };

  const ignoredAgents = new Set(["none", "bootstrap", "placeholder"]);

  const getAgentLabels = (msg: Message) => {
    const agents = msg.agents_used?.length
      ? msg.agents_used
      : (msg.agent_used || "").split(",");
    return agents
      .map((agent) => agent.trim())
      .filter((agent) => agent && !ignoredAgents.has(agent))
      .map((agent) => agentLabels[agent] || agent);
  };

  const formatMemoryValue = (hint: MemoryHint) => {
    const rawValue = hint.value !== undefined ? hint.value : hint.value_json;
    const value =
      rawValue &&
      typeof rawValue === "object" &&
      !Array.isArray(rawValue) &&
      "value" in rawValue
        ? (rawValue as { value?: unknown }).value
        : rawValue;
    if (value === null || value === undefined || value === "") return "chua ro";
    if (
      typeof value === "string" ||
      typeof value === "number" ||
      typeof value === "boolean"
    ) {
      return String(value);
    }
    if (Array.isArray(value)) {
      return value.map((item) => String(item)).join(", ");
    }
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  };

  const formatCitation = (source: ChatSource) => {
    const citation = source.citation;
    if (!citation) return source.source || source.title || "Nguồn pháp lý";
    if (typeof citation === "string") return citation;
    if (
      !(
        "doc_slug" in citation ||
        "dieu_number" in citation ||
        "khoan_number" in citation
      )
    ) {
      return source.source || source.title || "Nguồn pháp lý";
    }
    const parts = [
      citation.doc_slug,
      citation.dieu_number ? `Điều ${citation.dieu_number}` : null,
      citation.khoan_number ? `Khoản ${citation.khoan_number}` : null,
    ].filter(Boolean);
    return parts.join(" · ");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSend();
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Sparkles size={18} className="text-primary" />
        <div>
          <p className="text-sm font-semibold">Tư vấn BĐS AI</p>
          <p className="text-[10px] text-muted-foreground">
            Online · Trả lời ngay
          </p>
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4">
        {!hasSession && messages.length === 1 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <Bot size={48} className="text-muted-foreground/40 mb-4" />
            <h2 className="text-lg font-semibold mb-2">
              Trợ lý Bất động sản AI
            </h2>
            <p className="text-sm text-muted-foreground max-w-md">
              Hỏi tôi về giá nhà, thị trường, pháp lý, hoặc tìm bất động sản
              phù hợp với bạn.
            </p>
            <div className="flex flex-wrap gap-2 mt-4 justify-center">
              {messages[0].suggested_actions?.map((action) => (
                <button
                  key={action}
                  onClick={() => onSend(action)}
                  className="rounded-full border border-border px-3 py-1 text-xs hover:bg-muted transition-colors"
                >
                  {action}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="mx-auto max-w-3xl space-y-4">
          {messages.map((msg, i) => (
            <div key={i}>
              <div
                className={`flex gap-3 ${
                  msg.role === "user" ? "flex-row-reverse" : ""
                }`}
              >
                {/* Avatar */}
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                    msg.role === "user"
                      ? "bg-accent text-white"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  {msg.role === "user" ? (
                    <User size={15} />
                  ) : (
                    <Bot size={15} />
                  )}
                </div>
                {/* Bubble */}
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                    msg.role === "user"
                      ? "bg-accent text-white rounded-tr-md"
                      : "bg-muted text-card-foreground rounded-tl-md"
                  }`}
                >
                  {getAgentLabels(msg).length > 0 && (
                    <div className="mb-1.5 flex flex-wrap gap-1">
                      {getAgentLabels(msg).map((label) => (
                        <span
                          key={label}
                          className="inline-block rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary"
                        >
                          {label}
                        </span>
                      ))}
                    </div>
                  )}
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">
                    {msg.content}
                  </p>

                  {/* Trace summary */}
                  {msg.trace_summary && (
                    <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-border/70 bg-card/60 px-2 py-1 text-[11px] leading-snug text-muted-foreground">
                      {msg.trace_summary.intent && (
                        <span className="max-w-full truncate">
                          Intent: {String(msg.trace_summary.intent)}
                        </span>
                      )}
                      {typeof msg.trace_summary.source_count === "number" && (
                        <span className="shrink-0">
                          {msg.trace_summary.source_count} nguon
                        </span>
                      )}
                      {typeof msg.trace_summary.latency_ms === "number" && (
                        <span className="shrink-0">
                          {Math.round(msg.trace_summary.latency_ms)}ms
                        </span>
                      )}
                    </div>
                  )}

                  {/* Sources */}
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="mt-2 space-y-1.5 border-t border-border/70 pt-2">
                      {msg.sources.slice(0, 3).map((source, sourceIndex) => {
                        const key = `${source.type || "source"}-${source.product_id || source.id || sourceIndex}`;
                        const sourceKind = getSourceKind(source);
                        const isLegal = sourceKind === "legal";
                        const isMarket = sourceKind === "market";
                        const Icon = isLegal ? Scale : isMarket ? BarChart3 : Home;
                        const listingDetails = getListingSourceDetails(source);

                        return (
                          <div
                            key={key}
                            className="rounded-md bg-card/70 p-2 text-[11px] leading-snug"
                          >
                            <div className="flex items-start gap-1.5 font-medium">
                              <Icon size={12} className="mt-0.5 shrink-0" />
                              <span className="line-clamp-2">
                                {getSourceTitle(source)}
                              </span>
                            </div>
                            {isLegal ? (
                              <div className="mt-1 flex items-center gap-1 text-muted-foreground">
                                <FileText size={11} className="shrink-0" />
                                <span className="truncate">
                                  {formatCitation(source)}
                                </span>
                              </div>
                            ) : isMarket ? (
                              <div className="mt-1 flex items-center gap-1 text-muted-foreground">
                                <TrendingUp size={11} className="shrink-0" />
                                <span className="truncate">
                                  {getMarketSourceSummary(source)}
                                </span>
                              </div>
                            ) : (
                              <>
                                <div className="mt-1 flex items-center gap-1 text-muted-foreground">
                                  <MapPin size={11} className="shrink-0" />
                                  <span className="truncate">
                                    {source.location
                                      ? typeof source.location === "string"
                                        ? source.location
                                        : JSON.stringify(source.location)
                                      : "Chưa rõ vị trí"}
                                  </span>
                                </div>
                                <div className="mt-1 text-muted-foreground">
                                  {listingDetails.join(" · ")}
                                </div>
                              </>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
              {/* Suggested actions */}
              {msg.suggested_actions &&
                msg.suggested_actions.length > 0 && (
                  <div className="mt-2 ml-11 flex flex-wrap gap-1.5">
                    {msg.suggested_actions.map((action, j) => (
                      <button
                        key={j}
                        onClick={() => onSend(action)}
                        className="rounded-full border border-border bg-card px-3 py-1 text-xs text-foreground transition-colors hover:bg-primary hover:text-primary-foreground hover:border-primary"
                      >
                        {action}
                      </button>
                    ))}
                  </div>
                )}
            </div>
          ))}
          {loading && (
            <div className="flex gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
                <Bot size={15} />
              </div>
              <div className="rounded-2xl rounded-tl-md bg-muted px-4 py-3">
                <div className="flex gap-1">
                  <span
                    className="inline-block h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce"
                    style={{ animationDelay: "0ms" }}
                  />
                  <span
                    className="inline-block h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce"
                    style={{ animationDelay: "150ms" }}
                  />
                  <span
                    className="inline-block h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce"
                    style={{ animationDelay: "300ms" }}
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Input */}
      <div className="border-t border-border px-4 py-3">
        <form
          onSubmit={handleSubmit}
          className="mx-auto flex max-w-3xl items-center gap-2"
        >
          <input
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            placeholder="Hỏi về bất động sản..."
            className="flex-1 rounded-xl border border-border bg-muted px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-colors"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={!input.trim() || loading}
            className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground transition-colors hover:bg-primary-hover disabled:opacity-40"
          >
            <Send size={18} />
          </button>
        </form>
        <p className="mx-auto mt-2 max-w-3xl text-center text-[10px] text-muted-foreground">
          Trợ lý AI có thể mắc lỗi. Hãy kiểm tra thông tin quan trọng.
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify lint**

Run: `cd frontend && npm run lint`
Expected: No new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/chatbot/ChatPanel.tsx
git commit -m "feat: add ChatPanel for full-page chat UI"
```

---

### Task 9: Frontend — `/tro-ly-ai/page.tsx`

**Files:**
- Create: `frontend/app/tro-ly-ai/page.tsx`

- [ ] **Step 1: Create the landing page**

```typescript
"use client";

import { useChat } from "@/lib/useChat";
import ChatSidebar from "@/components/chatbot/ChatSidebar";
import ChatPanel from "@/components/chatbot/ChatPanel";

export default function TroLyAIPage() {
  const {
    messages,
    input,
    loading,
    sessionId,
    sessions,
    loadingSessions,
    scrollRef,
    setInput,
    send,
    selectSession,
    deleteSession,
    renameSession,
    newSession,
  } = useChat({ mode: "full" });

  return (
    <div className="flex h-[calc(100vh-64px)]">
      {/* Sidebar */}
      <ChatSidebar
        sessions={sessions}
        currentSessionId={sessionId}
        loading={loadingSessions}
        onSelect={selectSession}
        onDelete={deleteSession}
        onRename={renameSession}
        onNew={newSession}
      />

      {/* Main chat area */}
      <div className="flex-1 min-w-0">
        <ChatPanel
          messages={messages}
          input={input}
          loading={loading}
          scrollRef={scrollRef}
          onInputChange={setInput}
          onSend={send}
          hasSession={!!sessionId}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add metadata (optional, for SEO)**

Create `frontend/app/tro-ly-ai/layout.tsx` if you want page-specific metadata:

```typescript
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Trợ lý AI — Tư vấn Bất động sản",
  description:
    "Trò chuyện với trợ lý AI để tìm kiếm nhà đất, phân tích thị trường, tư vấn pháp lý và đầu tư.",
};
```

- [ ] **Step 3: Verify lint**

Run: `cd frontend && npm run lint`
Expected: No new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/tro-ly-ai/
git commit -m "feat: add /tro-ly-ai chatbot landing page"
```

---

### Task 10: Final verification & integration test

- [ ] **Step 1: Verify TypeScript compilation**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors.

- [ ] **Step 2: Verify lint**

Run: `cd frontend && npm run lint`
Expected: No errors.

- [ ] **Step 3: Verify Python syntax**

Run: `python -m compileall backend\app\routers\chat.py backend\app\schemas\chat.py`
Expected: Compilation successful.

- [ ] **Step 4: Manual test checklist**

1. Start servers: `docker-compose up -d`
2. Open `http://localhost:3000/tro-ly-ai`
3. Verify sidebar shows on left, chat panel on right
4. Send a message → verify response appears
5. Refresh page → verify session appears in sidebar (if logged in)
6. Click session in sidebar → verify history loads
7. Rename session → verify title updates
8. Delete session → verify it disappears
9. Click "Cuộc trò chuyện mới" → verify fresh chat
10. Open `http://localhost:3000` → ChatWidget appears, click expand → navigates to `/tro-ly-ai`
11. Anonymous user → chat works, sidebar empty/hidden

- [ ] **Step 5: Final commit (if any fixes)**

```bash
git add -A
git commit -m "chore: final integration fixes for /tro-ly-ai"
```
