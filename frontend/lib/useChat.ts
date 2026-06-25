"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import {
  sendChatMessage,
  getChatSessions,
  getChatSessionHistory,
  deleteChatSession,
  renameChatSession,
} from "@/lib/api";
import {
  buildDemoChatResponse,
  isDemoChatEnabled,
} from "@/lib/demoChatResponses";
import type {
  ChatMessageResponse,
  ChatSessionResponse,
  ChatSource,
} from "@/lib/types";
import {
  registryAsSessions,
  upsertConversation,
  removeConversation,
  getLastSessionId,
  setLastSessionId,
} from "@/lib/chatHistory";

export interface Message {
  role: "user" | "assistant";
  content: string;
  agent_used?: string | null;
  agents_used?: string[] | null;
  sources?: ChatSource[] | null;
  charts?: Record<string, unknown>[] | null;
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

  // Send message
  const send = useCallback(
    async (text?: string) => {
      const msg = text || input.trim();
      if (!msg || loading) return;

      setInput("");
      setMessages((prev) => [...prev, { role: "user", content: msg }]);
      setLoading(true);

      try {
        let res: ChatMessageResponse;
        if (isDemoChatEnabled()) {
          await new Promise((resolve) => setTimeout(resolve, 450));
          res = buildDemoChatResponse(
            msg,
            sessionId || `demo-session-${Date.now()}`
          );
        } else {
          res = await sendChatMessage({
            message: msg,
            session_id: sessionId || undefined,
          });
        }
        setSessionId(res.session_id);
        setLastSessionId(res.session_id);
        if (!localStorage.getItem("token")) {
          // First user message becomes the conversation title; later sends only
          // refresh updatedAt (upsert keeps the original title).
          upsertConversation(res.session_id, msg);
          if (isFull) loadSessions();
        }
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: res.content,
            agent_used: res.agent_used,
            agents_used: res.agents_used,
            sources: res.sources,
            charts: res.charts,
            suggested_actions: res.suggested_actions,
            trace_summary: res.trace_summary,
            memory_hints: res.memory_hints,
            feedback_id: res.feedback_id,
            request_id: res.request_id,
          },
        ]);
        // Refresh session list in full mode (logged-in path)
        if (isFull && !sessionId && localStorage.getItem("token")) {
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

  // Create new session — declared before selectSession so its catch can reference it
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
            charts: m.charts,
            suggested_actions: m.suggested_actions,
            trace_summary: m.trace_summary,
            memory_hints: m.memory_hints,
            feedback_id: m.feedback_id,
            request_id: m.request_id,
          }))
        );
      } catch {
        removeConversation(id); // stale id — drop it and start fresh
        newSession();
      } finally {
        setLoading(false);
      }
    },
    [isFull, newSession]
  );

  // Mount effect: load sessions and restore last conversation
  useEffect(() => {
    if (!isFull) return;
    loadSessions();
    const last = getLastSessionId();
    if (last) {
      selectSession(last); // restores messages + sets sessionId so chat continues it
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isFull]);

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
    [sessionId, newSession]
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
