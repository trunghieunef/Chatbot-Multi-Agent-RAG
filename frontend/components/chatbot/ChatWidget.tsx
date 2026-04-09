"use client";

import { useState, useRef, useEffect } from "react";
import { MessageCircle, X, Send, Bot, User, Sparkles } from "lucide-react";
import { sendChatMessage } from "@/lib/api";
import type { ChatMessageResponse } from "@/lib/types";

interface Message {
  role: "user" | "assistant";
  content: string;
  agent_used?: string | null;
  suggested_actions?: string[] | null;
}

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
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
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  async function handleSend(text?: string) {
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
          suggested_actions: res.suggested_actions,
        },
      ]);
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
  }

  const agentLabels: Record<string, string> = {
    property_search: "🏠 Tìm kiếm",
    market_analysis: "📊 Thị trường",
    legal_advisor: "⚖️ Pháp lý",
    investment_advisor: "💰 Đầu tư",
    placeholder: "🤖 AI",
  };

  return (
    <>
      {/* Floating Button */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-xl transition-transform hover:scale-110 animate-pulse-ring"
          aria-label="Mở chatbot"
        >
          <MessageCircle size={24} />
        </button>
      )}

      {/* Chat Panel */}
      {open && (
        <div className="fixed bottom-6 right-6 z-50 flex w-[380px] max-w-[calc(100vw-2rem)] flex-col rounded-2xl border border-border bg-card shadow-2xl animate-slide-in overflow-hidden"
             style={{ height: "min(560px, calc(100vh - 6rem))" }}>
          {/* Header */}
          <div className="flex items-center justify-between bg-gradient-to-r from-primary to-primary-hover px-4 py-3 text-primary-foreground">
            <div className="flex items-center gap-2">
              <Sparkles size={18} />
              <div>
                <p className="text-sm font-semibold">Tư vấn BĐS AI</p>
                <p className="text-[10px] opacity-80">Online · Trả lời ngay</p>
              </div>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="rounded-lg p-1 transition-colors hover:bg-white/20"
            >
              <X size={18} />
            </button>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
            {messages.map((msg, i) => (
              <div key={i}>
                <div
                  className={`flex gap-2 ${
                    msg.role === "user" ? "flex-row-reverse" : ""
                  }`}
                >
                  {/* Avatar */}
                  <div
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs ${
                      msg.role === "user"
                        ? "bg-accent text-white"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {msg.role === "user" ? (
                      <User size={14} />
                    ) : (
                      <Bot size={14} />
                    )}
                  </div>
                  {/* Bubble */}
                  <div
                    className={`max-w-[75%] rounded-xl px-3 py-2 text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-accent text-white rounded-tr-none"
                        : "bg-muted text-card-foreground rounded-tl-none"
                    }`}
                  >
                    {msg.agent_used &&
                      msg.agent_used !== "none" &&
                      msg.agent_used !== "placeholder" && (
                        <span className="mb-1 inline-block rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                          {agentLabels[msg.agent_used] || msg.agent_used}
                        </span>
                      )}
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  </div>
                </div>
                {/* Suggested actions */}
                {msg.suggested_actions && msg.suggested_actions.length > 0 && (
                  <div className="mt-2 ml-9 flex flex-wrap gap-1.5">
                    {msg.suggested_actions.map((action, j) => (
                      <button
                        key={j}
                        onClick={() => handleSend(action)}
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
              <div className="flex gap-2">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <Bot size={14} />
                </div>
                <div className="rounded-xl rounded-tl-none bg-muted px-4 py-3">
                  <div className="flex gap-1">
                    <span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "0ms" }} />
                    <span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "150ms" }} />
                    <span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <div className="border-t border-border p-3">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }}
              className="flex items-center gap-2"
            >
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Hỏi về bất động sản..."
                className="flex-1 rounded-lg border border-border bg-muted px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary focus:ring-1 focus:ring-primary/30 transition-colors"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={!input.trim() || loading}
                className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-colors hover:bg-primary-hover disabled:opacity-40"
              >
                <Send size={16} />
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
