"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowUpDown } from "lucide-react";
import { getListings } from "@/lib/api";
import FilterPanel from "@/components/search/FilterPanel";
import ListingGrid from "@/components/listing/ListingGrid";
import type { ListingCard, ListingFilters, PaginatedResponse } from "@/lib/types";

const SORT_OPTIONS = [
  { label: "Mới nhất", value: "newest" },
  { label: "Giá tăng dần", value: "price_asc" },
  { label: "Giá giảm dần", value: "price_desc" },
  { label: "Diện tích tăng", value: "area_asc" },
  { label: "Diện tích giảm", value: "area_desc" },
];

function ListingsPageContent({ listingType }: { listingType: string }) {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [filters, setFilters] = useState<ListingFilters>(() => {
    const f: ListingFilters = {
      listing_type: listingType,
      page: 1,
      limit: 12,
    };
    const s = searchParams.get("search");
    if (s) f.search = s;
    const pt = searchParams.get("property_type");
    if (pt) f.property_type = pt;
    const city = searchParams.get("city");
    if (city) f.city = city;
    return f;
  });

  const [data, setData] = useState<PaginatedResponse<ListingCard>>({
    items: [],
    total: 0,
    page: 1,
    limit: 12,
    total_pages: 0,
  });
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getListings(filters);
      setData(result);
    } catch {
      // API might not be running
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  function handleFilterChange(newFilters: ListingFilters) {
    setFilters(newFilters);
    // Update URL params
    const params = new URLSearchParams();
    if (newFilters.search) params.set("search", newFilters.search);
    if (newFilters.property_type) params.set("property_type", newFilters.property_type);
    if (newFilters.city) params.set("city", newFilters.city);
    if (newFilters.district) params.set("district", newFilters.district);
    const url = params.toString() ? `?${params.toString()}` : "";
    router.replace(url, { scroll: false });
  }

  function handlePageChange(page: number) {
    setFilters((prev) => ({ ...prev, page }));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const title = listingType === "sale" ? "Nhà đất bán" : "Nhà đất cho thuê";

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      {/* Breadcrumb */}
      <nav className="mb-4 text-xs text-muted-foreground">
        <Link href="/" className="hover:text-primary">
          Trang chủ
        </Link>
        <span className="mx-1.5">›</span>
        <span className="text-foreground font-medium">{title}</span>
      </nav>

      <h1 className="text-2xl font-bold text-foreground mb-6">{title}</h1>

      <div className="flex flex-col lg:flex-row gap-6">
        {/* Filter sidebar */}
        <FilterPanel
          filters={filters}
          onChange={handleFilterChange}
          listingType={listingType}
        />

        {/* Main content */}
        <div className="flex-1 min-w-0">
          {/* Sort bar */}
          <div className="mb-4 flex items-center justify-between rounded-xl border border-border bg-card px-4 py-2.5">
            <p className="text-xs text-muted-foreground">
              Sắp xếp theo
            </p>
            <div className="flex items-center gap-1">
              <ArrowUpDown size={14} className="text-muted-foreground" />
              <select
                value={filters.sort || "newest"}
                onChange={(e) =>
                  setFilters((prev) => ({ ...prev, sort: e.target.value, page: 1 }))
                }
                className="bg-transparent text-sm font-medium text-foreground outline-none cursor-pointer"
              >
                {SORT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Results grid */}
          <ListingGrid
            items={data.items}
            total={data.total}
            page={data.page}
            totalPages={data.total_pages}
            onPageChange={handlePageChange}
            loading={loading}
          />
        </div>
      </div>
    </div>
  );
}

export default function NhaDatBanPage() {
  return (
    <Suspense fallback={<div className="py-20 text-center text-muted-foreground">Đang tải...</div>}>
      <ListingsPageContent listingType="sale" />
    </Suspense>
  );
}
