"use client";

import { useEffect, useState } from "react";
import { Search, SlidersHorizontal, X } from "lucide-react";
import { getCategories, getCities, getDistricts } from "@/lib/api";
import type { ListingFilters } from "@/lib/types";

interface Props {
  filters: ListingFilters;
  onChange: (filters: ListingFilters) => void;
  listingType: string;
}

const PRICE_RANGES = [
  { label: "Tất cả mức giá", value: "" },
  { label: "Dưới 1 tỷ", min: 0, max: 1 },
  { label: "1 - 3 tỷ", min: 1, max: 3 },
  { label: "3 - 5 tỷ", min: 3, max: 5 },
  { label: "5 - 10 tỷ", min: 5, max: 10 },
  { label: "10 - 20 tỷ", min: 10, max: 20 },
  { label: "Trên 20 tỷ", min: 20, max: undefined },
];

const AREA_RANGES = [
  { label: "Tất cả diện tích", value: "" },
  { label: "Dưới 30 m²", min: 0, max: 30 },
  { label: "30 - 50 m²", min: 30, max: 50 },
  { label: "50 - 80 m²", min: 50, max: 80 },
  { label: "80 - 100 m²", min: 80, max: 100 },
  { label: "100 - 200 m²", min: 100, max: 200 },
  { label: "Trên 200 m²", min: 200, max: undefined },
];

const BEDROOMS = [
  { label: "Tất cả", value: undefined },
  { label: "1 PN", value: 1 },
  { label: "2 PN", value: 2 },
  { label: "3 PN", value: 3 },
  { label: "4 PN", value: 4 },
  { label: "5+ PN", value: 5 },
];

export default function FilterPanel({ filters, onChange, listingType }: Props) {
  const [categories, setCategories] = useState<string[]>([]);
  const [cities, setCities] = useState<{ name: string; count: number }[]>([]);
  const [districts, setDistricts] = useState<{ district: string; city: string; count: number }[]>([]);
  const [showMobile, setShowMobile] = useState(false);

  useEffect(() => {
    getCategories().then((d) => setCategories(d.items)).catch(() => {});
    getCities().then((d) => setCities(d.items)).catch(() => {});
  }, []);

  useEffect(() => {
    if (filters.city) {
      getDistricts(filters.city).then((d) => setDistricts(d.items)).catch(() => {});
    }
  }, [filters.city]);

  function update(partial: Partial<ListingFilters>) {
    onChange({ ...filters, ...partial, page: 1 });
  }

  function clearAll() {
    onChange({ listing_type: listingType, page: 1, limit: 12 });
  }

  const hasActiveFilters =
    filters.search || filters.property_type || filters.city || filters.district ||
    filters.min_price != null || filters.max_price != null ||
    filters.min_area != null || filters.max_area != null ||
    filters.bedrooms != null;
  const visibleDistricts = filters.city ? districts : [];

  const filterContent = (
    <div className="space-y-5">
      {/* Search */}
      <div>
        <label className="mb-1.5 block text-xs font-semibold text-foreground">
          Từ khóa
        </label>
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={filters.search || ""}
            onChange={(e) => update({ search: e.target.value })}
            placeholder="Tìm theo khu vực, dự án..."
            className="w-full rounded-lg border border-border bg-muted pl-9 pr-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary/30 transition-colors"
          />
        </div>
      </div>

      {/* Property type */}
      <div>
        <label className="mb-1.5 block text-xs font-semibold text-foreground">
          Loại nhà đất
        </label>
        <select
          value={filters.property_type || ""}
          onChange={(e) => update({ property_type: e.target.value || undefined })}
          className="w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm outline-none focus:border-primary transition-colors"
        >
          <option value="">Tất cả loại</option>
          {categories.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      {/* City */}
      <div>
        <label className="mb-1.5 block text-xs font-semibold text-foreground">
          Tỉnh / Thành phố
        </label>
        <select
          value={filters.city || ""}
          onChange={(e) => update({ city: e.target.value || undefined, district: undefined })}
          className="w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm outline-none focus:border-primary transition-colors"
        >
          <option value="">Tất cả</option>
          {cities.map((c) => (
            <option key={c.name} value={c.name}>
              {c.name} ({c.count})
            </option>
          ))}
        </select>
      </div>

      {/* District */}
      {visibleDistricts.length > 0 && (
        <div>
          <label className="mb-1.5 block text-xs font-semibold text-foreground">
            Quận / Huyện
          </label>
          <select
            value={filters.district || ""}
            onChange={(e) => update({ district: e.target.value || undefined })}
            className="w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm outline-none focus:border-primary transition-colors"
          >
            <option value="">Tất cả</option>
            {visibleDistricts.map((d) => (
              <option key={d.district} value={d.district}>
                {d.district} ({d.count})
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Price range */}
      <div>
        <label className="mb-1.5 block text-xs font-semibold text-foreground">
          Mức giá
        </label>
        <select
          value={
            filters.min_price != null
              ? `${filters.min_price}-${filters.max_price ?? ""}`
              : ""
          }
          onChange={(e) => {
            if (!e.target.value) {
              update({ min_price: undefined, max_price: undefined });
            } else {
              const [min, max] = e.target.value.split("-");
              update({
                min_price: min ? Number(min) : undefined,
                max_price: max ? Number(max) : undefined,
              });
            }
          }}
          className="w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm outline-none focus:border-primary transition-colors"
        >
          {PRICE_RANGES.map((r, i) => (
            <option key={i} value={r.value ?? `${r.min}-${r.max ?? ""}`}>
              {r.label}
            </option>
          ))}
        </select>
      </div>

      {/* Area range */}
      <div>
        <label className="mb-1.5 block text-xs font-semibold text-foreground">
          Diện tích
        </label>
        <select
          value={
            filters.min_area != null
              ? `${filters.min_area}-${filters.max_area ?? ""}`
              : ""
          }
          onChange={(e) => {
            if (!e.target.value) {
              update({ min_area: undefined, max_area: undefined });
            } else {
              const [min, max] = e.target.value.split("-");
              update({
                min_area: min ? Number(min) : undefined,
                max_area: max ? Number(max) : undefined,
              });
            }
          }}
          className="w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm outline-none focus:border-primary transition-colors"
        >
          {AREA_RANGES.map((r, i) => (
            <option key={i} value={r.value ?? `${r.min}-${r.max ?? ""}`}>
              {r.label}
            </option>
          ))}
        </select>
      </div>

      {/* Bedrooms */}
      <div>
        <label className="mb-1.5 block text-xs font-semibold text-foreground">
          Phòng ngủ
        </label>
        <div className="flex flex-wrap gap-1.5">
          {BEDROOMS.map((b) => (
            <button
              key={b.label}
              onClick={() => update({ bedrooms: b.value })}
              className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                filters.bedrooms === b.value
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-card text-foreground hover:bg-muted"
              }`}
            >
              {b.label}
            </button>
          ))}
        </div>
      </div>

      {/* Clear */}
      {hasActiveFilters && (
        <button
          onClick={clearAll}
          className="flex w-full items-center justify-center gap-1 rounded-lg border border-border py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted"
        >
          <X size={12} /> Xóa bộ lọc
        </button>
      )}
    </div>
  );

  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={() => setShowMobile(!showMobile)}
        className="mb-4 flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground lg:hidden transition-colors hover:bg-muted"
      >
        <SlidersHorizontal size={16} />
        Bộ lọc
        {hasActiveFilters && (
          <span className="ml-1 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-[10px] text-primary-foreground">
            !
          </span>
        )}
      </button>

      {/* Mobile overlay */}
      {showMobile && (
        <div className="fixed inset-0 z-40 bg-black/50 lg:hidden" onClick={() => setShowMobile(false)}>
          <div
            className="absolute right-0 top-0 h-full w-80 max-w-full overflow-y-auto bg-card p-5 shadow-xl animate-slide-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-foreground">Bộ lọc tìm kiếm</h3>
              <button onClick={() => setShowMobile(false)} className="p-1 hover:bg-muted rounded-lg">
                <X size={18} />
              </button>
            </div>
            {filterContent}
          </div>
        </div>
      )}

      {/* Desktop sidebar */}
      <aside className="hidden lg:block w-64 shrink-0">
        <div className="sticky top-20 rounded-xl border border-border bg-card p-4 shadow-sm">
          <h3 className="mb-4 text-sm font-bold text-foreground">
            Bộ lọc tìm kiếm
          </h3>
          {filterContent}
        </div>
      </aside>
    </>
  );
}
