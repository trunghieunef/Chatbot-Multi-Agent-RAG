/* ─── API Client for FastAPI Backend ─── */

import type {
  AdminAgentHealth,
  AdminFeedbackItem,
  AdminPipelineReadinessItem,
  AdminTraceDetail,
  AdminTraceListItem,
  ArticleCard,
  ArticleDetail,
  ArticleFilters,
  AuthUser,
  ChatFeedbackRequest,
  ChatHistoryResponse,
  ChatMessageRequest,
  ChatMessageResponse,
  ChatSessionResponse,
  CityCount,
  DistrictCount,
  ListingCard,
  ListingDetail,
  ListingFilters,
  LocationCount,
  MarketStats,
  PaginatedResponse,
  PriceByDistrict,
  ProjectCard,
  ProjectDetail,
  ProjectFilters,
  PropertyTypeCount,
  TokenResponse,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

function authHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function buildQuery(params: Record<string, unknown>): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `?${s}` : "";
}

/* ─── Listings ─── */

export async function getListings(
  filters: ListingFilters = {}
): Promise<PaginatedResponse<ListingCard>> {
  return fetchJSON(`${BASE}/listings${buildQuery({ ...filters })}`);
}

export async function getListingDetail(id: number): Promise<ListingDetail> {
  return fetchJSON(`${BASE}/listings/${id}`);
}

export async function getSimilarListings(
  id: number,
  limit = 6
): Promise<ListingCard[]> {
  return fetchJSON(`${BASE}/listings/similar/${id}?limit=${limit}`);
}

export async function getProjects(
  filters: ProjectFilters = {}
): Promise<PaginatedResponse<ProjectCard>> {
  return fetchJSON(`${BASE}/projects${buildQuery({ ...filters })}`);
}

export async function getProjectDetail(id: number): Promise<ProjectDetail> {
  return fetchJSON(`${BASE}/projects/${id}`);
}

export async function getArticles(
  filters: ArticleFilters = {}
): Promise<PaginatedResponse<ArticleCard>> {
  return fetchJSON(`${BASE}/articles${buildQuery({ ...filters })}`);
}

export async function getArticleDetail(id: number): Promise<ArticleDetail> {
  return fetchJSON(`${BASE}/articles/${id}`);
}

/* ─── Market ─── */

export async function getMarketStats(): Promise<MarketStats> {
  return fetchJSON(`${BASE}/market/stats`);
}

export async function getTopLocations(
  listing_type?: string,
  limit = 10
): Promise<{ items: LocationCount[] }> {
  return fetchJSON(
    `${BASE}/market/top-locations${buildQuery({ listing_type, limit })}`
  );
}

export async function getPriceByDistrict(
  city?: string,
  listing_type = "sale"
): Promise<{ items: PriceByDistrict[] }> {
  return fetchJSON(
    `${BASE}/market/price-by-district${buildQuery({ city, listing_type })}`
  );
}

export async function getPropertyTypes(
  listing_type?: string
): Promise<{ items: PropertyTypeCount[] }> {
  return fetchJSON(
    `${BASE}/market/property-types${buildQuery({ listing_type })}`
  );
}

export async function getCategories(): Promise<{ items: string[] }> {
  return fetchJSON(`${BASE}/market/categories`);
}

export async function getCities(): Promise<{ items: CityCount[] }> {
  return fetchJSON(`${BASE}/market/cities`);
}

export async function getDistricts(
  city?: string
): Promise<{ items: DistrictCount[] }> {
  return fetchJSON(`${BASE}/market/districts${buildQuery({ city })}`);
}

/* ─── Chat ─── */

export async function sendChatMessage(
  body: ChatMessageRequest
): Promise<ChatMessageResponse> {
  return fetchJSON(`${BASE}/chat`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
}

/* Streaming chat (SSE over fetch — POST + Bearer, so EventSource can't be used).
   Calls onNode as each graph node starts/completes, onFinal with the full
   ChatMessageResponse, onError on failure. Returns when the stream ends. */
export interface StreamHandlers {
  onNode?: (node: string, status: string) => void;
  onFinal?: (payload: ChatMessageResponse) => void;
  onError?: (message: string) => void;
}

export async function streamChatMessage(
  body: ChatMessageRequest,
  handlers: StreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`API ${res.status}: stream unavailable`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (raw: string) => {
    // One SSE record: lines "event: X" and "data: {...}".
    let eventName = "message";
    const dataLines: string[] = [];
    for (const line of raw.split("\n")) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    let evt: { payload?: Record<string, unknown> };
    try {
      evt = JSON.parse(dataLines.join("\n"));
    } catch {
      return;
    }
    const payload = evt.payload || {};
    if (eventName === "node_start") {
      handlers.onNode?.(String(payload.node ?? ""), String(payload.status ?? ""));
    } else if (eventName === "final") {
      handlers.onFinal?.(payload as unknown as ChatMessageResponse);
    } else if (eventName === "error") {
      handlers.onError?.(String(payload.message ?? "stream error"));
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE records are separated by a blank line.
    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const record = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      if (record.trim()) dispatch(record);
    }
  }
  if (buffer.trim()) dispatch(buffer);
}

/* Chat feedback */

export async function sendChatFeedback(
  body: ChatFeedbackRequest
): Promise<{ id: number }> {
  return fetchJSON(`${BASE}/chat/feedback`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
}

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

/* Admin */

export async function getAdminChatTraces(): Promise<AdminTraceListItem[]> {
  return fetchJSON(`${BASE}/admin/chat-traces`, {
    headers: authHeaders(),
  });
}

export async function getAdminPipelineReadiness(): Promise<{
  items: AdminPipelineReadinessItem[];
}> {
  const data = await fetchJSON<
    AdminPipelineReadinessItem[] | { items?: AdminPipelineReadinessItem[] }
  >(`${BASE}/admin/pipeline-readiness`, {
    headers: authHeaders(),
  });
  let items: AdminPipelineReadinessItem[] = [];
  if (Array.isArray(data)) {
    items = data;
  } else if (Array.isArray(data.items)) {
    items = data.items;
  }
  return { items };
}

export async function getAdminTraceDetail(
  requestId: string
): Promise<AdminTraceDetail> {
  return fetchJSON(`${BASE}/admin/chat-traces/${requestId}`, {
    headers: authHeaders(),
  });
}

export async function searchAdminTraces(params: {
  status?: string;
  intent?: string;
  q?: string;
  limit?: number;
}): Promise<{ items: AdminTraceListItem[]; total: number }> {
  const qs = buildQuery({
    status: params.status || undefined,
    intent: params.intent || undefined,
    q: params.q || undefined,
    limit: params.limit ?? 50,
  });
  return fetchJSON(`${BASE}/admin/chat-traces/search${qs}`, {
    headers: authHeaders(),
  });
}

export async function getAdminFeedback(): Promise<AdminFeedbackItem[]> {
  return fetchJSON(`${BASE}/admin/feedback`, { headers: authHeaders() });
}

export async function getAdminAgentHealth(): Promise<AdminAgentHealth> {
  return fetchJSON(`${BASE}/admin/agent-health`, { headers: authHeaders() });
}

/* ─── Auth ─── */

export async function login(
  email: string,
  password: string
): Promise<TokenResponse> {
  return fetchJSON(`${BASE}/auth/login`, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function register(body: {
  email: string;
  password: string;
  full_name: string;
}): Promise<TokenResponse> {
  return fetchJSON(`${BASE}/auth/register`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getMe(): Promise<AuthUser> {
  return fetchJSON(`${BASE}/auth/me`, {
    headers: authHeaders(),
  });
}
