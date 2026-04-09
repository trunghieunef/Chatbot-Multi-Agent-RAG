"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import ListingCard from "./ListingCard";
import type { ListingCard as ListingCardType } from "@/lib/types";

interface Props {
  items: ListingCardType[];
  total: number;
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  loading?: boolean;
}

function SkeletonCard() {
  return (
    <div className="flex flex-col rounded-xl border border-border bg-card overflow-hidden">
      <div className="h-44 skeleton" />
      <div className="p-4 space-y-3">
        <div className="h-4 w-3/4 skeleton" />
        <div className="h-5 w-1/3 skeleton" />
        <div className="flex gap-3">
          <div className="h-3 w-14 skeleton" />
          <div className="h-3 w-14 skeleton" />
        </div>
        <div className="h-3 w-1/2 skeleton" />
      </div>
    </div>
  );
}

export default function ListingGrid({
  items,
  total,
  page,
  totalPages,
  onPageChange,
  loading,
}: Props) {
  if (loading) {
    return (
      <div>
        <div className="mb-4 h-4 w-40 skeleton" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (!items.length) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <span className="text-5xl mb-4">🔍</span>
        <h3 className="text-lg font-semibold text-foreground">
          Không tìm thấy kết quả
        </h3>
        <p className="text-sm text-muted-foreground mt-1">
          Hãy thử đổi bộ lọc hoặc từ khóa tìm kiếm.
        </p>
      </div>
    );
  }

  return (
    <div>
      {/* Total count */}
      <p className="mb-4 text-sm text-muted-foreground">
        Tìm thấy{" "}
        <strong className="text-foreground">{total.toLocaleString()}</strong> tin
        đăng
      </p>

      {/* Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((listing, i) => (
          <ListingCard key={listing.id} listing={listing} index={i} />
        ))}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-8">
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="rounded-lg border border-border bg-card p-2 text-sm transition-colors hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <ChevronLeft size={16} />
          </button>

          {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
            let pageNum: number;
            if (totalPages <= 7) {
              pageNum = i + 1;
            } else if (page <= 4) {
              pageNum = i + 1;
            } else if (page >= totalPages - 3) {
              pageNum = totalPages - 6 + i;
            } else {
              pageNum = page - 3 + i;
            }
            return (
              <button
                key={pageNum}
                onClick={() => onPageChange(pageNum)}
                className={`h-9 min-w-[36px] rounded-lg border text-sm font-medium transition-colors ${
                  pageNum === page
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-card text-foreground hover:bg-muted"
                }`}
              >
                {pageNum}
              </button>
            );
          })}

          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
            className="rounded-lg border border-border bg-card p-2 text-sm transition-colors hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
