"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Search,
  TrendingUp,
  Building2,
  MapPin,
  ArrowRight,
  BarChart3,
  Shield,
  Sparkles,
} from "lucide-react";
import { getListings, getMarketStats, getPropertyTypes } from "@/lib/api";
import ListingCard from "@/components/listing/ListingCard";
import type { ListingCard as ListingCardType, MarketStats } from "@/lib/types";

export default function HomePage() {
  const [stats, setStats] = useState<MarketStats | null>(null);
  const [featured, setFeatured] = useState<ListingCardType[]>([]);
  const [propertyTypes, setPropertyTypes] = useState<{ property_type: string; count: number }[]>([]);
  const [search, setSearch] = useState("");

  useEffect(() => {
    getMarketStats().then(setStats).catch(() => {});
    getListings({ limit: 8, sort: "newest" }).then((d) => setFeatured(d.items)).catch(() => {});
    getPropertyTypes().then((d) => setPropertyTypes(d.items.slice(0, 6))).catch(() => {});
  }, []);

  return (
    <>
      {/* ─── Hero ──────────────────────────────────────────── */}
      <section className="relative overflow-hidden bg-gradient-to-br from-slate-900 via-slate-800 to-primary/20">
        {/* Decorative blobs */}
        <div className="absolute -top-20 -left-20 h-72 w-72 rounded-full bg-primary/20 blur-3xl" />
        <div className="absolute -bottom-10 right-0 h-60 w-60 rounded-full bg-accent/20 blur-3xl" />

        <div className="relative mx-auto max-w-7xl px-4 py-16 sm:py-24">
          <div className="text-center mb-10 animate-fade-in-up">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-4 py-1.5 text-xs font-medium text-white/80 backdrop-blur mb-4">
              <Sparkles size={12} /> Nền tảng BĐS tích hợp AI
            </span>
            <h1 className="text-3xl sm:text-5xl font-extrabold text-white leading-tight mb-4">
              Tìm bất động sản
              <br />
              <span className="bg-gradient-to-r from-red-400 to-orange-300 bg-clip-text text-transparent">
                phù hợp chỉ trong vài giây
              </span>
            </h1>
            <p className="mx-auto max-w-xl text-sm sm:text-base text-white/60">
              Hơn {stats?.total_listings?.toLocaleString() || "---"} tin đăng từ
              khắp Việt Nam. Tư vấn thông minh bởi chatbot AI đa tác nhân.
            </p>
          </div>

          {/* Search Panel */}
          <div className="mx-auto max-w-2xl rounded-2xl bg-white/10 backdrop-blur-xl border border-white/10 p-5 shadow-2xl animate-fade-in-up" style={{ animationDelay: "200ms" }}>
            {/* Tabs */}
            <div className="flex gap-1 mb-4">
              {["Nhà đất bán", "Nhà đất cho thuê"].map((tab, i) => (
                <Link
                  key={tab}
                  href={i === 0 ? "/nha-dat-ban" : "/nha-dat-cho-thue"}
                  className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                    i === 0
                      ? "bg-primary text-white"
                      : "text-white/60 hover:text-white hover:bg-white/10"
                  }`}
                >
                  {tab}
                </Link>
              ))}
            </div>

            {/* Search input */}
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search
                  size={16}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40"
                />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Tìm theo khu vực, dự án, đường phố..."
                  className="w-full rounded-lg bg-white/10 border border-white/10 pl-10 pr-4 py-3 text-sm text-white placeholder:text-white/40 outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20 transition-colors"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && search.trim()) {
                      window.location.href = `/nha-dat-ban?search=${encodeURIComponent(search)}`;
                    }
                  }}
                />
              </div>
              <Link
                href={`/nha-dat-ban${search ? `?search=${encodeURIComponent(search)}` : ""}`}
                className="rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-primary-hover flex items-center gap-1.5"
              >
                Tìm kiếm
              </Link>
            </div>
          </div>

          {/* Stats */}
          <div className="mx-auto mt-8 grid max-w-3xl grid-cols-2 sm:grid-cols-4 gap-4 animate-fade-in-up" style={{ animationDelay: "400ms" }}>
            {[
              {
                icon: <Building2 size={18} />,
                value: stats?.total_listings?.toLocaleString() || "---",
                label: "Tin đăng",
              },
              {
                icon: <MapPin size={18} />,
                value: stats?.total_districts?.toLocaleString() || "---",
                label: "Quận / huyện",
              },
              {
                icon: <TrendingUp size={18} />,
                value: stats?.average_price_billion
                  ? `${stats.average_price_billion} tỷ`
                  : "---",
                label: "Giá trung bình",
              },
              {
                icon: <BarChart3 size={18} />,
                value: stats?.total_cities?.toLocaleString() || "---",
                label: "Tỉnh / thành",
              },
            ].map((s, i) => (
              <div
                key={i}
                className="rounded-xl bg-white/5 backdrop-blur border border-white/10 px-4 py-3 text-center"
              >
                <div className="flex justify-center text-primary mb-1">
                  {s.icon}
                </div>
                <p className="text-lg font-bold text-white">{s.value}</p>
                <p className="text-[11px] text-white/50">{s.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Quick Links ───────────────────────────────────── */}
      {propertyTypes.length > 0 && (
        <section className="bg-background py-12">
          <div className="mx-auto max-w-7xl px-4">
            <div className="flex items-end justify-between mb-6">
              <div>
                <span className="text-xs font-semibold text-primary uppercase tracking-wider">
                  Khám phá nhanh
                </span>
                <h2 className="text-xl sm:text-2xl font-bold text-foreground">
                  Loại hình bất động sản
                </h2>
              </div>
              <Link
                href="/nha-dat-ban"
                className="flex items-center gap-1 text-sm font-medium text-primary hover:underline"
              >
                Xem tất cả <ArrowRight size={14} />
              </Link>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {propertyTypes.map((pt, i) => (
                <Link
                  key={pt.property_type}
                  href={`/nha-dat-ban?property_type=${encodeURIComponent(pt.property_type)}`}
                  className="group flex items-center gap-4 rounded-xl border border-border bg-card p-4 transition-all hover:border-primary/30 hover:shadow-md animate-fade-in-up"
                  style={{ animationDelay: `${i * 80}ms` }}
                >
                  <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-white">
                    <Building2 size={20} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-foreground truncate">
                      {pt.property_type}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {pt.count.toLocaleString()} tin đăng
                    </p>
                  </div>
                  <ArrowRight
                    size={16}
                    className="text-muted-foreground transition-transform group-hover:translate-x-1 group-hover:text-primary"
                  />
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ─── Featured Listings ─────────────────────────────── */}
      <section className="bg-muted/50 py-12">
        <div className="mx-auto max-w-7xl px-4">
          <div className="flex items-end justify-between mb-6">
            <div>
              <span className="text-xs font-semibold text-primary uppercase tracking-wider">
                Tin đăng mới
              </span>
              <h2 className="text-xl sm:text-2xl font-bold text-foreground">
                Bất động sản nổi bật
              </h2>
            </div>
            <Link
              href="/nha-dat-ban"
              className="flex items-center gap-1 text-sm font-medium text-primary hover:underline"
            >
              Xem tất cả <ArrowRight size={14} />
            </Link>
          </div>

          {featured.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {featured.map((listing, i) => (
                <ListingCard key={listing.id} listing={listing} index={i} />
              ))}
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="rounded-xl border border-border bg-card overflow-hidden">
                  <div className="h-44 skeleton" />
                  <div className="p-4 space-y-3">
                    <div className="h-4 w-3/4 skeleton" />
                    <div className="h-5 w-1/3 skeleton" />
                    <div className="h-3 w-1/2 skeleton" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* ─── CTA Section ───────────────────────────────────── */}
      <section className="py-16">
        <div className="mx-auto max-w-7xl px-4">
          <div className="rounded-2xl bg-gradient-to-r from-slate-900 to-slate-800 p-8 sm:p-12 text-center relative overflow-hidden">
            <div className="absolute top-0 right-0 h-40 w-40 rounded-full bg-primary/20 blur-3xl" />
            <div className="relative">
              <h2 className="text-2xl sm:text-3xl font-bold text-white mb-3">
                Chatbot AI tư vấn bất động sản 24/7
              </h2>
              <p className="text-sm sm:text-base text-white/60 max-w-xl mx-auto mb-6">
                Hệ thống multi-agent RAG với 4 chuyên gia: Tìm kiếm BĐS, Phân
                tích thị trường, Tư vấn pháp lý, Đầu tư. Hỏi bất cứ điều gì!
              </p>
              <div className="flex flex-wrap justify-center gap-3 text-sm">
                {[
                  { icon: <Search size={14} />, text: "Tìm nhà thông minh" },
                  { icon: <BarChart3 size={14} />, text: "Phân tích thị trường" },
                  { icon: <Shield size={14} />, text: "Tư vấn pháp lý" },
                  { icon: <TrendingUp size={14} />, text: "Đầu tư sinh lời" },
                ].map((item, i) => (
                  <span
                    key={i}
                    className="flex items-center gap-1.5 rounded-full bg-white/10 px-4 py-2 text-white/80 backdrop-blur"
                  >
                    {item.icon} {item.text}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
