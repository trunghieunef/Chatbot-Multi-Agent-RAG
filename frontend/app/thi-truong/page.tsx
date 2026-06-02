"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { BarChart3, TrendingUp, Building2, MapPin } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import {
  getMarketStats,
  getPriceByDistrict,
  getTopLocations,
  getPropertyTypes,
  getCities,
} from "@/lib/api";
import type {
  MarketStats,
  PriceByDistrict,
  LocationCount,
  PropertyTypeCount,
} from "@/lib/types";

const COLORS = [
  "#e03c31", "#1e40af", "#10b981", "#f59e0b", "#8b5cf6",
  "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#6366f1",
];

export default function MarketPage() {
  const [stats, setStats] = useState<MarketStats | null>(null);
  const [priceData, setPriceData] = useState<PriceByDistrict[]>([]);
  const [topLocs, setTopLocs] = useState<LocationCount[]>([]);
  const [propTypes, setPropTypes] = useState<PropertyTypeCount[]>([]);
  const [cities, setCities] = useState<{ name: string; count: number }[]>([]);
  const [selectedCity, setSelectedCity] = useState<string>("");

  useEffect(() => {
    getMarketStats().then(setStats).catch(() => {});
    getPriceByDistrict().then((d) => setPriceData(d.items.slice(0, 15))).catch(() => {});
    getTopLocations(undefined, 10).then((d) => setTopLocs(d.items)).catch(() => {});
    getPropertyTypes().then((d) => setPropTypes(d.items)).catch(() => {});
    getCities().then((d) => setCities(d.items)).catch(() => {});
  }, []);

  useEffect(() => {
    getPriceByDistrict(selectedCity || undefined)
      .then((d) => setPriceData(d.items.slice(0, 15)))
      .catch(() => {});
  }, [selectedCity]);

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      {/* Breadcrumb */}
      <nav className="mb-4 text-xs text-muted-foreground">
        <Link href="/" className="hover:text-primary">Trang chủ</Link>
        <span className="mx-1.5">›</span>
        <span className="text-foreground font-medium">Dữ liệu thị trường</span>
      </nav>

      <h1 className="text-2xl font-bold text-foreground mb-6">
        📊 Dữ liệu thị trường bất động sản
      </h1>

      {/* Stats Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        {[
          {
            icon: <Building2 size={20} />,
            label: "Tổng tin đăng",
            value: stats?.total_listings?.toLocaleString() || "---",
            color: "text-primary",
            bg: "bg-primary/10",
          },
          {
            icon: <TrendingUp size={20} />,
            label: "Giá trung bình",
            value: stats?.average_price_billion ? `${stats.average_price_billion} tỷ` : "---",
            color: "text-accent-light",
            bg: "bg-accent-light/10",
          },
          {
            icon: <MapPin size={20} />,
            label: "Tỉnh / Thành phố",
            value: stats?.total_cities?.toLocaleString() || "---",
            color: "text-success",
            bg: "bg-success/10",
          },
          {
            icon: <BarChart3 size={20} />,
            label: "Quận / Huyện",
            value: stats?.total_districts?.toLocaleString() || "---",
            color: "text-warning",
            bg: "bg-warning/10",
          },
        ].map((card, i) => (
          <div
            key={i}
            className="rounded-xl border border-border bg-card p-5 shadow-sm animate-fade-in-up"
            style={{ animationDelay: `${i * 100}ms` }}
          >
            <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${card.bg} ${card.color} mb-3`}>
              {card.icon}
            </div>
            <p className="text-2xl font-bold text-foreground">{card.value}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{card.label}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Price by District Chart */}
        <div className="lg:col-span-2 rounded-xl border border-border bg-card p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-bold text-foreground">
              Giá trung bình theo quận/huyện
            </h2>
            <select
              value={selectedCity}
              onChange={(e) => setSelectedCity(e.target.value)}
              className="rounded-lg border border-border bg-muted px-3 py-1.5 text-xs outline-none focus:border-primary transition-colors"
            >
              <option value="">Tất cả</option>
              {cities.map((c) => (
                <option key={c.name} value={c.name}>{c.name}</option>
              ))}
            </select>
          </div>

          {priceData.length > 0 ? (
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={priceData} margin={{ top: 5, right: 10, bottom: 60, left: 5 }}>
                <XAxis
                  dataKey="district"
                  tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
                  angle={-45}
                  textAnchor="end"
                  interval={0}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
                  tickFormatter={(v: number) => `${v.toFixed(1)}`}
                />
                <Tooltip
                  formatter={(value) => [`${Number(value).toFixed(2)} tỷ`, "Giá TB"]}
                  labelFormatter={(label) => `Quận: ${label}`}
                  contentStyle={{
                    background: "var(--card)",
                    border: "1px solid var(--border)",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                />
                <Bar dataKey="avg_price" fill="var(--primary)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-[350px] items-center justify-center text-sm text-muted-foreground">
              Đang tải dữ liệu...
            </div>
          )}
        </div>

        {/* Property Type Pie */}
        <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <h2 className="text-sm font-bold text-foreground mb-4">
            Phân bổ loại hình BĐS
          </h2>
          {propTypes.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={propTypes.slice(0, 6)}
                  dataKey="count"
                  nameKey="property_type"
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  label={({ name, percent }: { name?: string; percent?: number }) =>
                    `${(name ?? "").slice(0, 10)} ${((percent ?? 0) * 100).toFixed(0)}%`
                  }
                  labelLine={false}
                  fontSize={9}
                >
                  {propTypes.slice(0, 6).map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value) => [Number(value).toLocaleString(), "Tin đăng"]}
                  contentStyle={{
                    background: "var(--card)",
                    border: "1px solid var(--border)",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-[300px] items-center justify-center text-sm text-muted-foreground">
              Đang tải...
            </div>
          )}
        </div>
      </div>

      {/* Top Locations Table */}
      <div className="mt-6 rounded-xl border border-border bg-card p-5 shadow-sm">
        <h2 className="text-sm font-bold text-foreground mb-4">
          Top khu vực nhiều tin đăng nhất
        </h2>
        {topLocs.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="pb-2 font-medium">#</th>
                  <th className="pb-2 font-medium">Quận / Huyện</th>
                  <th className="pb-2 font-medium">Tỉnh / TP</th>
                  <th className="pb-2 font-medium text-right">Số tin</th>
                  <th className="pb-2 font-medium">Tỷ lệ</th>
                </tr>
              </thead>
              <tbody>
                {topLocs.map((loc, i) => {
                  const total = topLocs.reduce((s, l) => s + l.count, 0);
                  const pct = ((loc.count / total) * 100).toFixed(1);
                  return (
                    <tr key={i} className="border-b border-border/50 last:border-0">
                      <td className="py-2.5 text-muted-foreground">{i + 1}</td>
                      <td className="py-2.5 font-medium text-foreground">{loc.district}</td>
                      <td className="py-2.5 text-muted-foreground">{loc.city}</td>
                      <td className="py-2.5 text-right font-semibold text-foreground">
                        {loc.count.toLocaleString()}
                      </td>
                      <td className="py-2.5">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-20 rounded-full bg-muted overflow-hidden">
                            <div
                              className="h-full rounded-full bg-primary"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <span className="text-xs text-muted-foreground">{pct}%</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-8 text-center text-sm text-muted-foreground">
            Đang tải dữ liệu...
          </div>
        )}
      </div>
    </div>
  );
}
