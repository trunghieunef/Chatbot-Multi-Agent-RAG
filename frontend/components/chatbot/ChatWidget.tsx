"use client";

import { useState } from "react";
import { BarChart3, ExternalLink, FileText, Home, MapPin, Maximize2, MessageCircle, Scale, Send, Bot, TrendingUp, User, Sparkles, X } from "lucide-react";
import { useChat } from "@/lib/useChat";
import { getListingSourceDetails, getMarketSourceSummary, getSourceKind, getSourceTitle, getSourceImages, getListingDetailHref } from "@/lib/chatSourceDisplay";
import { useRouter } from "next/navigation";
import ListingImageGallery from "./ListingImageGallery";
import type { ChatSource, MemoryHint, StructuredWarning } from "@/lib/types";
import type { Message } from "@/lib/useChat";

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
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
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

  const isStructuredWarning = (warning: unknown): warning is StructuredWarning =>
    Boolean(
      warning &&
        typeof warning === "object" &&
        "code" in warning &&
        "message" in warning
    );

  const getTraceWarnings = (trace: Message["trace_summary"]) =>
    Array.isArray(trace?.warnings)
      ? trace.warnings
          .map((warning) => {
            if (typeof warning === "string") return warning;
            if (isStructuredWarning(warning)) return warning.message || warning.code;
            return null;
          })
          .filter((warning): warning is string => Boolean(warning))
      : [];

  const formatCitation = (source: ChatSource) => {
    const citation = source.citation;
    if (!citation) return source.source || source.title || "Nguồn pháp lý";
    if (typeof citation === "string") return citation;
    if (!("doc_slug" in citation || "dieu_number" in citation || "khoan_number" in citation)) {
      return source.source || source.title || "Nguồn pháp lý";
    }
    const parts = [
      citation.doc_slug,
      citation.dieu_number ? `Điều ${citation.dieu_number}` : null,
      citation.khoan_number ? `Khoản ${citation.khoan_number}` : null,
    ].filter(Boolean);
    return parts.join(" · ");
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
        <div className="fixed bottom-4 left-4 right-4 z-50 flex flex-col rounded-2xl border border-border bg-card shadow-2xl animate-slide-in overflow-hidden sm:bottom-6 sm:left-auto sm:right-6 sm:w-[380px]"
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
            <div className="flex items-center gap-1">
              <button
                onClick={() => router.push("/tro-ly-ai")}
                className="rounded-lg p-1 transition-colors hover:bg-white/20"
                title="Mo rong"
              >
                <Maximize2 size={16} />
              </button>
              <button
                onClick={() => setOpen(false)}
                className="rounded-lg p-1 transition-colors hover:bg-white/20"
              >
                <X size={18} />
              </button>
            </div>
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
                    {getAgentLabels(msg).length > 0 && (
                      <div className="mb-1 flex flex-wrap gap-1">
                        {getAgentLabels(msg).map((label) => (
                          <span key={label} className="inline-block rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                            {label}
                          </span>
                        ))}
                      </div>
                    )}
                    <p className="whitespace-pre-wrap">{msg.content}</p>
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
                        {getTraceWarnings(msg.trace_summary).length > 0 && (
                          <span className="max-w-full truncate text-warning">
                            Canh bao: {getTraceWarnings(msg.trace_summary).slice(0, 2).join(", ")}
                          </span>
                        )}
                      </div>
                    )}
                    {msg.memory_hints && msg.memory_hints.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {msg.memory_hints.slice(0, 2).map((hint, hintIndex) => (
                          <div
                            key={`${hint.id ?? hint.key}-${hintIndex}`}
                            className="rounded-md border border-primary/20 bg-primary/5 px-2 py-1 text-[11px] leading-snug"
                          >
                            <div className="flex min-w-0 items-center justify-between gap-2">
                              <span className="truncate font-medium text-primary">
                                {hint.action}: {hint.key}
                              </span>
                              {typeof hint.confidence === "number" && (
                                <span className="shrink-0 text-muted-foreground">
                                  {Math.round(hint.confidence * 100)}%
                                </span>
                              )}
                            </div>
                            <p className="mt-0.5 line-clamp-2 break-words text-muted-foreground">
                              {formatMemoryValue(hint)}
                            </p>
                          </div>
                        ))}
                      </div>
                    )}
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-2 space-y-1.5 border-t border-border/70 pt-2">
                        {msg.sources.map((source, sourceIndex) => {
                          const key = `${source.type || "source"}-${source.product_id || source.id || sourceIndex}`;
                          const sourceKind = getSourceKind(source);
                          const isLegal = sourceKind === "legal";
                          const isMarket = sourceKind === "market";
                          const Icon = isLegal ? Scale : isMarket ? BarChart3 : Home;
                          const listingDetails = getListingSourceDetails(source);

                          return (
                            <div key={key} className="rounded-md bg-card/70 p-2 text-[11px] leading-snug">
                              <div className="flex items-start gap-1.5 font-medium">
                                <Icon size={12} className="mt-0.5 shrink-0" />
                                <span className="line-clamp-2">{getSourceTitle(source)}</span>
                              </div>
                              {isLegal ? (
                                <div className="mt-1 flex items-center gap-1 text-muted-foreground">
                                  <FileText size={11} className="shrink-0" />
                                  <span className="truncate">{formatCitation(source)}</span>
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
                                  <ListingImageGallery
                                    images={getSourceImages(source)}
                                  />
                                  {getListingDetailHref(source) && (
                                    <a
                                      href={getListingDetailHref(source)}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="mt-1 inline-flex items-center gap-1 text-primary hover:underline"
                                    >
                                      <ExternalLink size={11} className="shrink-0" />
                                      Xem chi tiết
                                    </a>
                                  )}
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
                {msg.suggested_actions && msg.suggested_actions.length > 0 && (
                  <div className="mt-2 ml-9 flex flex-wrap gap-1.5">
                    {msg.suggested_actions.map((action, j) => (
                      <button
                        key={j}
                        onClick={() => send(action)}
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
                send();
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
