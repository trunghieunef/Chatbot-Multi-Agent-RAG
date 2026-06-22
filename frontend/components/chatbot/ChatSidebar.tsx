"use client";

import { useState, useMemo } from "react";
import {
  MessageSquare,
  Plus,
  Pencil,
  Trash2,
  Search,
  Check,
} from "lucide-react";
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

  const timeAgo = useMemo(
    () => (dateStr: string | null) => {
      if (!dateStr) return "";
      const diff = Date.now() - new Date(dateStr).getTime();
      const mins = Math.floor(diff / 60000);
      if (mins < 60) return `${mins} phút`;
      const hours = Math.floor(mins / 60);
      if (hours < 24) return `${hours} giờ`;
      const days = Math.floor(hours / 24);
      return `${days} ngày`;
    },
    []
  );

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
                            onRename(
                              s.id,
                              editTitle || s.title || "Untitled"
                            );
                            setEditingId(null);
                          }
                          if (e.key === "Escape") setEditingId(null);
                        }}
                        onClick={(e) => e.stopPropagation()}
                      />
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onRename(
                            s.id,
                            editTitle || s.title || "Untitled"
                          );
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
