"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  Database,
  DollarSign,
  Star,
  Loader2,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import {
  getAdminChatTraces,
  getAdminPipelineReadiness,
  getAdminFeedback,
  getAdminAgentHealth,
} from "@/lib/api";
import type {
  AdminTraceListItem,
  AdminPipelineReadinessItem,
  AdminFeedbackItem,
  AdminAgentHealth,
} from "@/lib/types";

type TabKey = "data" | "traces" | "feedback" | "cost";

const TABS: { key: TabKey; label: string; icon: typeof Database }[] = [
  { key: "data", label: "Trạng thái dữ liệu", icon: Database },
  { key: "traces", label: "Vết tác tử", icon: Activity },
  { key: "feedback", label: "Phản hồi người dùng", icon: Star },
  { key: "cost", label: "Chi phí LLM", icon: DollarSign },
];

function fmtDate(v?: string | null): string {
  if (!v) return "—";
  const d = new Date(v);
  return isNaN(d.getTime()) ? "—" : d.toLocaleString("vi-VN");
}

function StatusPill({ status }: { status?: string | null }) {
  const s = (status || "").toLowerCase();
  const good = ["ready", "success", "completed", "ok"].includes(s);
  const bad = ["error", "failed", "stale", "unavailable"].includes(s);
  const cls = good
    ? "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400"
    : bad
    ? "bg-rose-500/12 text-rose-600 dark:text-rose-400"
    : "bg-amber-500/12 text-amber-600 dark:text-amber-400";
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${cls}`}>
      {status || "unknown"}
    </span>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  sublabel,
}: {
  icon: typeof Database;
  label: string;
  value: string;
  sublabel?: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon size={15} />
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <div className="mt-2 text-2xl font-semibold tabular-nums text-foreground">{value}</div>
      {sublabel && <div className="text-xs text-muted-foreground">{sublabel}</div>}
    </div>
  );
}

export default function AdminDashboard() {
  const router = useRouter();
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const [tab, setTab] = useState<TabKey>("data");

  const [traces, setTraces] = useState<AdminTraceListItem[]>([]);
  const [readiness, setReadiness] = useState<AdminPipelineReadinessItem[]>([]);
  const [feedback, setFeedback] = useState<AdminFeedbackItem[]>([]);
  const [health, setHealth] = useState<AdminAgentHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [t, r, f, h] = await Promise.all([
        getAdminChatTraces(),
        getAdminPipelineReadiness(),
        getAdminFeedback(),
        getAdminAgentHealth(),
      ]);
      setTraces(t);
      setReadiness(r.items);
      setFeedback(f);
      setHealth(h);
      setAuthorized(true);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      // Backend guards with 403; anything auth-ish → not an admin → send home.
      if (msg.includes("403") || msg.includes("401")) {
        setAuthorized(false);
        router.replace("/dang-nhap");
        return;
      }
      setError("Không tải được dữ liệu quản trị. Thử lại sau.");
      setAuthorized(true);
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  const avgLatency = useMemo(() => {
    if (!traces.length) return 0;
    const total = traces.reduce((s, t) => s + Number(t.latency_ms || 0), 0);
    return Math.round(total / traces.length);
  }, [traces]);

  const readySources = readiness.filter((s) => (s.status || "") === "ready").length;
  const positiveFeedback = feedback.filter((f) =>
    ["positive", "up"].includes((f.rating || "").toLowerCase())
  ).length;
  const cost = health?.llm_cost;
  const budgetPct =
    cost && cost.monthly_budget_usd
      ? Math.round((cost.estimated_cost_usd / cost.monthly_budget_usd) * 100)
      : null;

  if (authorized === false) {
    return null; // redirecting
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-foreground">Bảng quản trị</h1>
        <p className="text-sm text-muted-foreground">
          Giám sát dữ liệu, tác tử, phản hồi và chi phí LLM
        </p>
      </header>

      {/* KPI row */}
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          icon={Database}
          label="Nguồn sẵn sàng"
          value={loading ? "—" : `${readySources}/${readiness.length}`}
          sublabel="đã lập chỉ mục"
        />
        <StatCard
          icon={Activity}
          label="Vết tác tử"
          value={loading ? "—" : traces.length.toLocaleString("vi-VN")}
          sublabel={`${avgLatency.toLocaleString("vi-VN")} ms trung bình`}
        />
        <StatCard
          icon={Star}
          label="Phản hồi tích cực"
          value={loading ? "—" : `${positiveFeedback}/${feedback.length}`}
          sublabel="lượt đánh giá"
        />
        <StatCard
          icon={DollarSign}
          label="Chi phí LLM tháng"
          value={loading || !cost ? "—" : `$${cost.estimated_cost_usd.toFixed(2)}`}
          sublabel={budgetPct !== null ? `${budgetPct}% ngân sách` : "chưa có ngân sách"}
        />
      </div>

      {/* Tabs */}
      <div className="mb-4 flex flex-wrap gap-1 border-b border-border">
        {TABS.map((t) => {
          const active = t.key === tab;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
                active
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              <t.icon size={15} />
              {t.label}
            </button>
          );
        })}
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-rose-500/30 bg-rose-500/8 px-4 py-3 text-sm text-rose-600 dark:text-rose-400">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="animate-spin" size={18} />
          Đang tải…
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          {tab === "data" && <DataTab items={readiness} />}
          {tab === "traces" && <TracesTab items={traces} />}
          {tab === "feedback" && <FeedbackTab items={feedback} />}
          {tab === "cost" && <CostTab health={health} traces={traces} />}
        </div>
      )}
    </div>
  );
}

/* ── Tab 1: Data status ───────────────────────────────── */
function DataTab({ items }: { items: AdminPipelineReadinessItem[] }) {
  if (!items.length) return <Empty label="Chưa có dữ liệu nguồn." />;
  return (
    <table className="w-full min-w-[720px] text-sm">
      <THead cols={["Nguồn", "Trạng thái", "Bản ghi gốc", "Chunks", "Cập nhật gần nhất"]} />
      <tbody>
        {items.map((s, i) => (
          <tr key={s.id ?? i} className="border-t border-border">
            <Td className="font-medium">{s.source_name || "—"}</Td>
            <Td><StatusPill status={s.status} /></Td>
            <Td className="tabular-nums">{(s.parent_count ?? 0).toLocaleString("vi-VN")}</Td>
            <Td className="tabular-nums">{(s.chunk_count ?? 0).toLocaleString("vi-VN")}</Td>
            <Td className="text-muted-foreground">{fmtDate(s.last_indexed_at || s.updated_at)}</Td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ── Tab 2: Traces ────────────────────────────────────── */
function TracesTab({ items }: { items: AdminTraceListItem[] }) {
  if (!items.length) return <Empty label="Chưa có vết tác tử nào." />;
  return (
    <table className="w-full min-w-[820px] text-sm">
      <THead cols={["Thời gian", "Intent", "Tác tử", "Latency", "Trạng thái", "Request ID"]} />
      <tbody>
        {items.slice(0, 50).map((t) => {
          const summaryIntent = t.trace_summary_json?.intent;
          const intent =
            t.intent || (typeof summaryIntent === "string" ? summaryIntent : "unknown");
          return (
            <tr key={t.id} className="border-t border-border">
              <Td className="whitespace-nowrap text-muted-foreground">{fmtDate(t.created_at)}</Td>
              <Td>{intent}</Td>
              <Td className="text-muted-foreground">
                {(t.agents_used || []).map(String).join(", ") || "—"}
              </Td>
              <Td className="whitespace-nowrap tabular-nums">
                {Math.round(Number(t.latency_ms || 0)).toLocaleString("vi-VN")} ms
              </Td>
              <Td><StatusPill status={t.status} /></Td>
              <Td className="font-mono text-xs text-muted-foreground">
                {t.request_id.slice(0, 8)}…
              </Td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/* ── Tab 3: Feedback ──────────────────────────────────── */
function FeedbackTab({ items }: { items: AdminFeedbackItem[] }) {
  if (!items.length) return <Empty label="Chưa có phản hồi nào." />;
  return (
    <table className="w-full min-w-[680px] text-sm">
      <THead cols={["Thời gian", "Đánh giá", "Nhận xét", "Request ID"]} />
      <tbody>
        {items.map((f, i) => {
          const r = (f.rating || "").toLowerCase();
          const good = ["positive", "up"].includes(r);
          const bad = ["negative", "down"].includes(r);
          return (
            <tr key={f.id ?? i} className="border-t border-border">
              <Td className="whitespace-nowrap text-muted-foreground">{fmtDate(f.created_at)}</Td>
              <Td>
                <span
                  className={
                    good
                      ? "text-emerald-600 dark:text-emerald-400"
                      : bad
                      ? "text-rose-600 dark:text-rose-400"
                      : ""
                  }
                >
                  {good ? "👍 Hài lòng" : bad ? "👎 Không hài lòng" : f.rating || "—"}
                </span>
              </Td>
              <Td className="max-w-md text-muted-foreground">{f.comment || "—"}</Td>
              <Td className="font-mono text-xs text-muted-foreground">
                {(f.request_id || "").slice(0, 8) || "—"}
              </Td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/* ── Tab 4: LLM cost ──────────────────────────────────── */
function CostTab({
  health,
  traces,
}: {
  health: AdminAgentHealth | null;
  traces: AdminTraceListItem[];
}) {
  const cost = health?.llm_cost;
  const chartData = (health?.items || []).map((it) => ({
    status: it.status,
    latency: Math.round(it.avg_latency_ms),
    count: it.count,
  }));
  const barColor = (status: string) =>
    ["success", "completed"].includes(status.toLowerCase())
      ? "#10b981"
      : ["error", "failed"].includes(status.toLowerCase())
      ? "#f43f5e"
      : "#f59e0b";

  return (
    <div className="p-4">
      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard
          icon={DollarSign}
          label="Chi phí ước tính"
          value={cost ? `$${cost.estimated_cost_usd.toFixed(4)}` : "—"}
          sublabel={cost?.month ? `tháng ${cost.month}` : undefined}
        />
        <StatCard
          icon={DollarSign}
          label="Ngân sách tháng"
          value={cost?.monthly_budget_usd ? `$${cost.monthly_budget_usd.toFixed(0)}` : "—"}
          sublabel={cost?.budget_exceeded ? "⚠️ đã vượt" : "trong hạn mức"}
        />
        <StatCard
          icon={Activity}
          label="Theo dõi chi phí"
          value={cost?.tracking_available ? "Bật" : "Tắt"}
          sublabel="Redis cost tracker"
        />
      </div>

      <h3 className="mb-2 text-sm font-medium text-foreground">
        Latency trung bình theo trạng thái
      </h3>
      {chartData.length ? (
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
              <XAxis dataKey="status" tick={{ fontSize: 12 }} stroke="currentColor" opacity={0.5} />
              <YAxis
                tick={{ fontSize: 12 }}
                stroke="currentColor"
                opacity={0.5}
                unit="ms"
                width={56}
              />
              <Tooltip
                formatter={(v) => [`${v} ms`, "Latency TB"]}
                contentStyle={{ fontSize: 12, borderRadius: 8 }}
              />
              <Bar dataKey="latency" radius={[4, 4, 0, 0]}>
                {chartData.map((d) => (
                  <Cell key={d.status} fill={barColor(d.status)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <Empty label="Chưa có dữ liệu latency." />
      )}
      <p className="mt-2 text-xs text-muted-foreground">
        Dựa trên {traces.length.toLocaleString("vi-VN")} vết tác tử gần đây.
      </p>
    </div>
  );
}

/* ── shared bits ──────────────────────────────────────── */
function THead({ cols }: { cols: string[] }) {
  return (
    <thead>
      <tr className="bg-muted/40 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {cols.map((c) => (
          <th key={c} className="px-4 py-2.5">
            {c}
          </th>
        ))}
      </tr>
    </thead>
  );
}
function Td({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <td className={`px-4 py-2.5 align-top ${className}`}>{children}</td>;
}
function Empty({ label }: { label: string }) {
  return <div className="px-4 py-12 text-center text-sm text-muted-foreground">{label}</div>;
}
