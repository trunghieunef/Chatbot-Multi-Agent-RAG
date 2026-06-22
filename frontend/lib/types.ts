/* ─── TypeScript interfaces matching backend Pydantic schemas ─── */

export interface ListingCard {
  id: number;
  product_id: string;
  listing_type: string | null;
  property_type: string | null;
  title: string | null;
  price_text: string | null;
  price_per_m2_text: string | null;
  area_text: string | null;
  bedrooms: number | null;
  bathrooms: number | null;
  district: string | null;
  city: string | null;
  address: string | null;
  contact_name: string | null;
  post_date: string | null;
  badge: string | null;
  url: string | null;
  primary_image_url: string | null;
  image_urls: string[];
}

export interface ListingDetail extends ListingCard {
  description: string | null;
  price: number | null;
  price_unit: string | null;
  price_per_m2: number | null;
  area: number | null;
  floors: number | null;
  direction: string | null;
  balcony_direction: string | null;
  frontage: string | null;
  road_width: string | null;
  legal_status: string | null;
  furniture: string | null;
  ward: string | null;
  latitude: number | null;
  longitude: number | null;
  contact_phone: string | null;
  expiry_date: string | null;
  created_at: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface MarketStats {
  total_listings: number;
  average_price_billion: number | null;
  average_area_m2: number | null;
  listings_for_sale: number;
  listings_for_rent: number;
  total_cities: number;
  total_districts: number;
}

export interface LocationCount {
  city: string;
  district: string;
  count: number;
}

export interface PriceByDistrict {
  city: string;
  district: string;
  count: number;
  avg_price: number | null;
  min_price: number | null;
  max_price: number | null;
  avg_price_per_m2: number | null;
}

export interface PropertyTypeCount {
  property_type: string;
  count: number;
}

export interface CityCount {
  name: string;
  count: number;
}

export interface DistrictCount {
  district: string;
  city: string;
  count: number;
}

export interface ChatMessageRequest {
  message: string;
  session_id?: string;
}

export interface ChatSource {
  type?: "listing" | "project" | "article" | "market_metric" | "legal_article" | "market_aggregate" | "district_comparison" | "investment_aggregate" | string;
  domain?: "property" | "project" | "news" | "legal" | "market" | string | null;
  id?: number | string;
  product_id?: string | null;
  title?: string | null;
  location?: string | Record<string, unknown> | null;
  snippet?: string | null;
  price_text?: string | null;
  area_text?: string | null;
  published_at?: string | null;
  source?: string | null;
  category?: string | null;
  url?: string | null;
  citation?: {
    doc_slug?: string;
    dieu_number?: number | string;
    khoan_number?: number | string;
  } | string | Record<string, unknown> | null;
  count?: number;
  filters?: Record<string, unknown>;
  items?: Array<Record<string, unknown>>;
  sale?: Record<string, unknown>;
  rent?: Record<string, unknown>;
  rental_yield_percent?: number | null;
  score?: number | null;
  metadata?: Record<string, unknown>;
}

export interface StructuredWarning {
  code: string;
  domain?: string | null;
  message: string;
  retryable?: boolean;
  details?: Record<string, unknown>;
}

export interface TraceSummary {
  intent: string | null;
  agents: string[];
  source_count: number;
  latency_ms: number;
  warnings: Array<string | StructuredWarning>;
  [key: string]: unknown;
}

export interface MemoryHint {
  id?: number;
  request_id?: string;
  action: string;
  key: string;
  value?: unknown;
  value_json?: unknown;
  confidence: number;
  evidence: string;
  requires_user_confirmation: boolean;
  status?: string;
  [key: string]: unknown;
}

export interface ChatMessageResponse {
  session_id: string;
  role: string;
  content: string;
  agent_used: string | null;
  agents_used?: string[] | null;
  sources: ChatSource[] | null;
  suggested_actions: string[] | null;
  trace_summary?: Partial<TraceSummary> | null;
  memory_hints?: MemoryHint[] | null;
  feedback_id?: string | null;
  request_id?: string | null;
  created_at: string | null;
}

export interface ChatFeedbackRequest {
  session_id: string;
  request_id: string;
  rating: "positive" | "negative" | "neutral" | "up" | "down" | string;
  issue_type?: string | null;
  comment?: string | null;
  metadata_json?: Record<string, unknown>;
}

export interface AdminTraceListItem {
  id: number;
  request_id: string;
  session_id: string | null;
  user_id: number | null;
  intent: string | null;
  agents_used: unknown[];
  trace_summary_json: Partial<TraceSummary> & Record<string, unknown>;
  latency_ms: number;
  status: string;
  error_message?: string | null;
  graph_version?: string | null;
  prompt_version?: string | null;
  model_name?: string | null;
  created_at?: string | null;
}

export interface AdminPipelineReadinessItem {
  id?: number;
  source_name?: string;
  status?: string;
  parent_count?: number;
  chunk_count?: number;
  last_indexed_at?: string | null;
  details_json?: Record<string, unknown>;
  warning?: string | null;
  updated_at?: string | null;
  [key: string]: unknown;
}

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

export interface AuthUser {
  id: number;
  email: string;
  full_name: string | null;
  phone: string | null;
  avatar_url: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface ListingFilters {
  search?: string;
  listing_type?: string;
  property_type?: string;
  city?: string;
  district?: string;
  min_price?: number;
  max_price?: number;
  min_area?: number;
  max_area?: number;
  bedrooms?: number;
  bathrooms?: number;
  direction?: string;
  sort?: string;
  page?: number;
  limit?: number;
}

export interface ProjectCard {
  id: number;
  name: string;
  slug: string | null;
  developer: string | null;
  location: string | null;
  district: string | null;
  city: string | null;
  total_units: number | null;
  price_range: string | null;
  area_range: string | null;
  status: string | null;
  project_type: string | null;
  description: string | null;
  amenities: string[];
  url: string | null;
  primary_image_url: string | null;
  image_urls: string[];
  created_at: string | null;
  updated_at: string | null;
}

export type ProjectDetail = ProjectCard;

export interface ProjectFilters {
  search?: string;
  city?: string;
  district?: string;
  project_type?: string;
  status?: string;
  sort?: string;
  page?: number;
  limit?: number;
}

export interface ArticleCard {
  id: number;
  title: string;
  body: string | null;
  summary: string | null;
  category: string | null;
  source: string | null;
  post_date: string | null;
  url: string | null;
  primary_image_url: string | null;
  image_urls: string[];
  created_at: string | null;
  updated_at: string | null;
}

export type ArticleDetail = ArticleCard;

export interface ArticleFilters {
  search?: string;
  category?: string;
  sort?: string;
  page?: number;
  limit?: number;
}
