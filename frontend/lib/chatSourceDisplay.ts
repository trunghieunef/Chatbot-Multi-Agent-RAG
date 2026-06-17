import type { ChatSource } from "./types";

export type ChatSourceKind = "legal" | "market" | "property";

const metadataValue = (source: ChatSource, key: string) => source.metadata?.[key];

const metadataText = (source: ChatSource, key: string) => {
  const value = metadataValue(source, key);
  return typeof value === "string" && value.trim() ? value : null;
};

export function getSourceKind(source: ChatSource): ChatSourceKind {
  if (source.domain === "legal" || source.type === "legal_article") {
    return "legal";
  }
  if (
    source.domain === "market" ||
    source.type === "market_metric" ||
    source.type === "district_comparison" ||
    source.type?.includes("aggregate")
  ) {
    return "market";
  }
  return "property";
}

export function getSourceTitle(source: ChatSource): string {
  const kind = getSourceKind(source);
  if (kind === "legal") {
    return source.title || source.source || "Nguon phap ly";
  }
  if (kind === "market") {
    return source.type === "investment_aggregate"
      ? "Tong hop dau tu"
      : "Thong ke thi truong";
  }
  return source.title || "Tin bat dong san";
}

export function getMarketSourceSummary(source: ChatSource): string {
  if (source.rental_yield_percent) {
    return `Rental yield ${source.rental_yield_percent}%/nam`;
  }
  if (source.count !== undefined) {
    return `${source.count} tin du lieu`;
  }

  const metric = metadataText(source, "metric");
  const value = metadataValue(source, "value");
  const unit = metadataText(source, "unit");
  if (metric && (typeof value === "number" || typeof value === "string")) {
    return `${metric}: ${unit ? `${value} ${unit}` : value}`;
  }

  return "Du lieu tong hop";
}

export function getListingSourceDetails(source: ChatSource): string[] {
  return [
    source.price_text || metadataText(source, "price_text"),
    source.area_text || metadataText(source, "area_text"),
  ].filter((value): value is string => Boolean(value));
}
