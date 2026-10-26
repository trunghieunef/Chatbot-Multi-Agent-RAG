"use client";

interface ComparisonRow {
  title?: string;
  url?: string | null;
  price_text?: string;
  area_text?: string;
  price_per_m2?: number | null;
  bedrooms?: number | null;
  bathrooms?: number | null;
  legal_status?: string | null;
  furniture?: string | null;
  location?: string;
  tags?: string[];
  pct_vs_area_avg?: number | null;
}

interface ComparisonTableSpec {
  title?: string;
  unit?: string;
  rows: ComparisonRow[];
}

const dash = (v: unknown) =>
  v === null || v === undefined || v === "" ? "—" : String(v);

export default function ComparisonTable({ table }: { table: Record<string, unknown> }) {
  const spec = table as unknown as ComparisonTableSpec;
  if (!spec || !Array.isArray(spec.rows) || spec.rows.length === 0) return null;

  const assess = (r: ComparisonRow) => {
    const parts = [...(r.tags ?? [])];
    if (typeof r.pct_vs_area_avg === "number") {
      const sign = r.pct_vs_area_avg > 0 ? "+" : "";
      parts.push(`${sign}${r.pct_vs_area_avg}% so TB khu vực`);
    }
    return parts.length ? parts.join(" · ") : "—";
  };

  const headers = ["Tin", "Giá", "Diện tích", "Giá/m²", "PN/WC", "Pháp lý", "Vị trí", "Nội thất", "Đánh giá"];

  return (
    <div className="mt-2 overflow-x-auto rounded-md border border-border/70">
      <table className="w-full text-[11px]">
        <thead className="bg-card/70 text-muted-foreground">
          <tr>
            {headers.map((h) => (
              <th key={h} className="whitespace-nowrap px-2 py-1 text-left font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {spec.rows.map((r, i) => (
            <tr key={i} className="border-t border-border/50 align-top">
              <td className="max-w-[160px] px-2 py-1">
                {r.url ? (
                  <a
                    href={r.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="line-clamp-2 text-primary hover:underline"
                  >
                    {dash(r.title)}
                  </a>
                ) : (
                  <span className="line-clamp-2">{dash(r.title)}</span>
                )}
              </td>
              <td className="whitespace-nowrap px-2 py-1">{dash(r.price_text)}</td>
              <td className="whitespace-nowrap px-2 py-1">{dash(r.area_text)}</td>
              <td className="whitespace-nowrap px-2 py-1">
                {typeof r.price_per_m2 === "number"
                  ? `${r.price_per_m2} ${spec.unit ?? ""}`.trim()
                  : "—"}
              </td>
              <td className="whitespace-nowrap px-2 py-1">
                {dash(r.bedrooms)}/{dash(r.bathrooms)}
              </td>
              <td className="px-2 py-1">{dash(r.legal_status)}</td>
              <td className="px-2 py-1">{dash(r.location)}</td>
              <td className="px-2 py-1">{dash(r.furniture)}</td>
              <td className="px-2 py-1">{assess(r)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
