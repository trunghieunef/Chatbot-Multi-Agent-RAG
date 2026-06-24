"use client";

import {
  BarChart3,
  ExternalLink,
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
import {
  getListingSourceDetails,
  getListingDetailHref,
  getMarketSourceSummary,
  getSourceImages,
  getSourceKind,
  getSourceTitle,
} from "@/lib/chatSourceDisplay";
import ListingImageGallery from "./ListingImageGallery";
import type { ChatSource } from "@/lib/types";
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
                        const Icon = isLegal
                          ? Scale
                          : isMarket
                            ? BarChart3
                            : Home;
                        const listingDetails =
                          getListingSourceDetails(source);

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
                                <TrendingUp
                                  size={11}
                                  className="shrink-0"
                                />
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
