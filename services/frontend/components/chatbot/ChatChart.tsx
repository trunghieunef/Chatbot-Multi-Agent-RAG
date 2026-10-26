"use client";

import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

interface ChartSpec {
  type: "line_band" | "bar";
  title?: string;
  unit?: string;
  x_key: string;
  data: Record<string, number | string>[];
}

export default function ChatChart({ chart }: { chart: Record<string, unknown> }) {
  const spec = chart as unknown as ChartSpec;
  if (!spec || !Array.isArray(spec.data) || spec.data.length === 0) return null;

  return (
    <div className="rounded-md border border-border/70 bg-card/60 p-2">
      {spec.title && (
        <div className="mb-1 text-[11px] font-medium text-foreground">
          {spec.title}
          {spec.unit ? ` (${spec.unit})` : ""}
        </div>
      )}
      <ResponsiveContainer width="100%" height={180}>
        {spec.type === "line_band" ? (
          <LineChart data={spec.data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey={spec.x_key} tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} width={32} />
            <Tooltip />
            <Line type="monotone" dataKey="max" stroke="var(--muted-foreground)" strokeDasharray="4 4" strokeWidth={1} dot={false} />
            <Line type="monotone" dataKey="min" stroke="var(--muted-foreground)" strokeDasharray="4 4" strokeWidth={1} dot={false} />
            <Line type="monotone" dataKey="avg" stroke="var(--primary)" strokeWidth={2} dot={false} />
          </LineChart>
        ) : (
          <BarChart data={spec.data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey={spec.x_key} tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} width={32} />
            <Tooltip />
            <Bar dataKey="avg" fill="var(--primary)" radius={[4, 4, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
