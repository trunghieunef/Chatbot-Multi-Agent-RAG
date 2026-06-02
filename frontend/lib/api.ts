/* ─── API Client for FastAPI Backend ─── */

import type {
  ListingCard,
  ListingDetail,
  PaginatedResponse,
  MarketStats,
  LocationCount,
  PriceByDistrict,
  PropertyTypeCount,
  CityCount,
  DistrictCount,
  ChatMessageRequest,
  ChatMessageResponse,
  ListingFilters,
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
    body: JSON.stringify(body),
  });
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
