"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, Database, MessageSquare, ShieldCheck } from "lucide-react";
import { getAdminChatTraces, getAdminPipelineReadiness } from "@/lib/api";
import type {
  AdminPipelineReadinessItem,
  AdminTraceListItem,
} from "@/lib/types";

function formatDate(value?: string | null) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function traceIntent(trace: AdminTraceListItem) {
  const summaryIntent = trace.trace_summary_json?.intent;
  return trace.intent || (typeof summaryIntent === "string" ? summaryIntent : "unknown");
}

function statusClass(status: string) {
  if (status === "success" || status === "ready") {
    return "bg-success/10 text-success";
  }
  if (status === "error" || status === "failed" || status === "missing") {
    return "bg-primary/10 text-primary";
  }
  return "bg-muted text-muted-foreground";
}

export default function AdminDashboard() {
  const [traces, setTraces] = useState<AdminTraceListItem[]>([]);
  const [readiness, setReadiness] = useState<AdminPipelineReadinessItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [traceData, readinessData] = await Promise.all([
          getAdminChatTraces(),
          getAdminPipelineReadiness(),
        ]);
        if (!cancelled) {
          setTraces(traceData);
          setReadiness(readinessData.items);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Khong tai duoc admin data");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const averageLatency = useMemo(() => {
    if (!traces.length) return 0;
    const total = traces.reduce((sum, trace) => sum + Number(trace.latency_ms || 0), 0);
    return Math.round(total / traces.length);
  }, [traces]);

  const readySources = readiness.filter((item) => item.status === "ready").length;

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold text-foreground">
            Agent Admin
          </h1>
          <p className="text-sm text-muted-foreground">
            Trace, readiness, and chat quality
          </p>
        </div>
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <ShieldCheck size={20} />
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 text-sm text-primary">
          {error}
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-3">
        {[
          {
            label: "Chat traces",
            value: loading ? "--" : traces.length.toLocaleString(),
            sublabel: "recent requests",
            icon: MessageSquare,
          },
          {
            label: "Readiness rows",
            value: loading ? "--" : readiness.length.toLocaleString(),
            sublabel: `${readySources} ready`,
            icon: Database,
          },
          {
            label: "Avg latency",
            value: loading ? "--" : `${averageLatency}ms`,
            sublabel: "trace mean",
            icon: Activity,
          },
        ].map((metric) => {
          const Icon = metric.icon;
          return (
            <section
              key={metric.label}
              className="rounded-lg border border-border bg-card p-4 shadow-sm"
            >
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="truncate text-sm font-medium text-muted-foreground">
                    {metric.label}
                  </h2>
                  <p className="mt-1 text-2xl font-semibold text-foreground">
                    {metric.value}
                  </p>
                </div>
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-primary">
                  <Icon size={18} />
                </div>
              </div>
              <p className="truncate text-xs text-muted-foreground">
                {metric.sublabel}
              </p>
            </section>
          );
        })}
      </div>

      <section className="mt-5 rounded-lg border border-border bg-card shadow-sm">
        <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-foreground">Recent traces</h2>
          <span className="text-xs text-muted-foreground">
            {loading ? "Loading" : `${traces.length} rows`}
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50 text-left text-xs text-muted-foreground">
                <th className="px-4 py-2 font-medium">Request</th>
                <th className="px-4 py-2 font-medium">Intent</th>
                <th className="px-4 py-2 font-medium text-right">Latency</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {traces.slice(0, 20).map((trace) => (
                <tr
                  key={trace.request_id}
                  className="border-b border-border/60 last:border-0"
                >
                  <td className="max-w-[260px] px-4 py-2">
                    <span className="block truncate font-mono text-xs text-foreground">
                      {trace.request_id}
                    </span>
                  </td>
                  <td className="max-w-[180px] px-4 py-2">
                    <span className="block truncate">{traceIntent(trace)}</span>
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {Math.round(Number(trace.latency_ms || 0))}ms
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={`inline-flex max-w-[120px] items-center rounded-full px-2 py-0.5 text-xs font-medium ${statusClass(trace.status)}`}
                    >
                      <span className="truncate">{trace.status}</span>
                    </span>
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {formatDate(trace.created_at)}
                  </td>
                </tr>
              ))}
              {!loading && traces.length === 0 && (
                <tr>
                  <td
                    className="px-4 py-8 text-center text-sm text-muted-foreground"
                    colSpan={5}
                  >
                    No traces
                  </td>
                </tr>
              )}
              {loading && (
                <tr>
                  <td
                    className="px-4 py-8 text-center text-sm text-muted-foreground"
                    colSpan={5}
                  >
                    Loading
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
