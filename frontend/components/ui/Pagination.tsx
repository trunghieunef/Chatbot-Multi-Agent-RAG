"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export default function Pagination({ page, totalPages, onPageChange }: PaginationProps) {
  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-center gap-2 mt-8">
      <button
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        aria-label="Trang trước"
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
        aria-label="Trang sau"
        className="rounded-lg border border-border bg-card p-2 text-sm transition-colors hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <ChevronRight size={16} />
      </button>
    </div>
  );
}
