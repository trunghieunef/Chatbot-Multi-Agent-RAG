"use client";

import { useState } from "react";
import ComparisonTable from "./ComparisonTable";

export default function ComparisonToggle({ table }: { table: Record<string, unknown> }) {
  const spec = table as { rows?: unknown[]; auto_open?: boolean };
  const [open, setOpen] = useState(spec.auto_open === true);
  const count = Array.isArray(spec.rows) ? spec.rows.length : 0;
  if (count < 2) return null;

  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="rounded-full border border-border bg-card px-3 py-1 text-xs text-foreground transition-colors hover:border-primary hover:bg-primary hover:text-primary-foreground"
      >
        {open ? "Ẩn so sánh" : `So sánh ${count} căn`}
      </button>
      {open && <ComparisonTable table={table} />}
    </div>
  );
}
