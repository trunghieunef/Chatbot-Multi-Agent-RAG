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

export interface ChatMessageResponse {
  session_id: string;
  role: string;
  content: string;
  agent_used: string | null;
  sources: Record<string, unknown>[] | null;
  suggested_actions: string[] | null;
  created_at: string | null;
}

export interface ChatSessionResponse {
  id: string;
  title: string | null;
  message_count: number;
  created_at: string | null;
  updated_at: string | null;
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
