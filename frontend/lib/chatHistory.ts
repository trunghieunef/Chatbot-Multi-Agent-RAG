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
  messageCount: number;
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
  return readRegistry();
}

export function upsertConversation(id: string, title: string): void {
  if (typeof window === "undefined") return;
  const entries = readRegistry();
  const now = new Date().toISOString();
  const existing = entries.find((e) => e.id === id);
  if (existing) {
    existing.updatedAt = now; // keep the original title
    existing.messageCount += 1;
  } else {
    const clean = title.trim().slice(0, TITLE_MAX) || "Cuộc trò chuyện";
    entries.push({ id, title: clean, updatedAt: now, messageCount: 1 });
  }
  writeRegistry(entries);
}

export function renameConversation(id: string, title: string): void {
  if (typeof window === "undefined") return;
  const entries = readRegistry();
  const entry = entries.find((e) => e.id === id);
  if (!entry) return;
  entry.title = title.trim().slice(0, TITLE_MAX) || entry.title;
  writeRegistry(entries);
}

export function removeConversation(id: string): void {
  if (typeof window === "undefined") return;
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
export function registryAsSessions(): ChatSessionResponse[] {
  return listConversations().map((e) => ({
    id: e.id,
    title: e.title,
    message_count: e.messageCount,
    created_at: e.updatedAt,
    updated_at: e.updatedAt,
  }));
}
