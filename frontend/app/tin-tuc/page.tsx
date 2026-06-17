"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  CalendarDays,
  Newspaper,
  Search,
  TrendingUp,
} from "lucide-react";
import { getArticles } from "@/lib/api";
import type { ArticleCard, ArticleFilters } from "@/lib/types";

const FALLBACK_ARTICLES: ArticleCard[] = [
  {
    id: 8001,
    title: "Thi truong nha o do thi lon tiep tuc phan hoa",
    body: null,
    summary:
      "Nguoi mua uu tien san pham co phap ly ro, tien ich hoan thien va kha nang khai thac cho thue on dinh.",
    category: "market",
    source: "batdongsan.com",
    post_date: "2026-06-15",
    url: null,
    created_at: null,
    updated_at: null,
  },
  {
    id: 8002,
    title: "Kinh nghiem doc thong tin quy hoach truoc khi xuong tien",
    body: null,
    summary:
      "Kiem tra quy hoach, ha tang va lo trinh phap ly giup nha dau tu giam rui ro khi mua bat dong san.",
    category: "guide",
    source: "batdongsan.com",
    post_date: "2026-06-12",
    url: null,
    created_at: null,
    updated_at: null,
  },
  {
    id: 8003,
    title: "Ha tang moi tao luc day cho khu Dong",
    body: null,
    summary:
      "Cac tuyen vanh dai, metro va truc ket noi lien vung tiep tuc la bien so quan trong cua gia nha dat.",
    category: "planning",
    source: "batdongsan.com",
    post_date: "2026-06-09",
    url: null,
    created_at: null,
    updated_at: null,
  },
  {
    id: 8004,
    title: "Can ho vua tui tien van giu thanh khoan tot",
    body: null,
    summary:
      "Phan khuc co tong gia hop ly, vi tri gan viec lam va tien ich co ban van duoc nguoi mua thuc quan tam.",
    category: "news",
    source: "batdongsan.com",
    post_date: "2026-06-05",
    url: null,
    created_at: null,
    updated_at: null,
  },
];

const CATEGORIES = [
  { value: "", label: "Tat ca", icon: Newspaper },
  { value: "market", label: "Thi truong", icon: TrendingUp },
  { value: "guide", label: "Huong dan", icon: BookOpen },
  { value: "planning", label: "Quy hoach", icon: CalendarDays },
];

function categoryLabel(category: string | null): string {
  const labels: Record<string, string> = {
    market: "Thi truong",
    guide: "Huong dan",
    planning: "Quy hoach",
    news: "Tin tuc",
  };
  return category ? labels[category] || category : "Tin tuc";
}

function formatDate(value: string | null): string {
  if (!value) return "Moi cap nhat";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function articleSummary(article: ArticleCard): string {
  return (
    article.summary ||
    article.body ||
    "Noi dung bai viet dang duoc cap nhat tu he thong crawl tin tuc."
  );
}

function ArticleCardItem({ article }: { article: ArticleCard }) {
  const href = article.url || `/tin-tuc?article=${article.id}`;

  return (
    <article className="group rounded-lg border border-border bg-card p-4 shadow-sm transition-all hover:border-primary/40 hover:shadow-md">
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-1 text-[11px] font-semibold text-primary">
          <Newspaper size={12} />
          {categoryLabel(article.category)}
        </span>
        <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
          <CalendarDays size={12} />
          {formatDate(article.post_date)}
        </span>
      </div>

      <h2 className="line-clamp-2 text-base font-bold leading-6 text-foreground">
        {article.title}
      </h2>
      <p className="mt-3 line-clamp-3 text-sm leading-6 text-muted-foreground">
        {articleSummary(article)}
      </p>

      <div className="mt-4 flex items-center justify-between gap-3">
        <span className="text-xs text-muted-foreground">
          {article.source || "batdongsan.com"}
        </span>
        <a
          href={href}
          target={article.url ? "_blank" : undefined}
          rel={article.url ? "noreferrer" : undefined}
          className="inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
        >
          Doc tiep <ArrowRight size={14} />
        </a>
      </div>
    </article>
  );
}

export default function NewsPage() {
  const [filters, setFilters] = useState<ArticleFilters>({
    sort: "newest",
    limit: 12,
  });
  const [draftSearch, setDraftSearch] = useState("");
  const [articles, setArticles] = useState<ArticleCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [usingFallback, setUsingFallback] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getArticles(filters)
      .then((data) => {
        if (cancelled) return;
        setArticles(data.items.length > 0 ? data.items : FALLBACK_ARTICLES);
        setUsingFallback(data.items.length === 0);
      })
      .catch(() => {
        if (cancelled) return;
        setArticles(FALLBACK_ARTICLES);
        setUsingFallback(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [filters]);

  const featured = articles[0] || FALLBACK_ARTICLES[0];
  const secondaryArticles = articles.slice(1);

  const sourceStats = useMemo(() => {
    const counts = new Map<string, number>();
    articles.forEach((article) => {
      const key = categoryLabel(article.category);
      counts.set(key, (counts.get(key) || 0) + 1);
    });
    return Array.from(counts.entries()).slice(0, 4);
  }, [articles]);

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters((current) => ({ ...current, search: draftSearch.trim(), page: 1 }));
  }

  return (
    <div className="bg-background">
      <section className="border-b border-border bg-card">
        <div className="mx-auto max-w-7xl px-4 py-8">
          <nav className="mb-5 text-xs text-muted-foreground">
            <Link href="/" className="hover:text-primary">
              Trang chu
            </Link>
            <span className="mx-1.5">/</span>
            <span className="font-medium text-foreground">Tin tuc</span>
          </nav>

          <div className="grid gap-6 lg:grid-cols-[1fr_360px] lg:items-end">
            <div>
              <span className="inline-flex items-center gap-2 rounded-md bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                <Newspaper size={14} />
                Tin tuc bat dong san
              </span>
              <h1 className="mt-4 text-3xl font-extrabold text-foreground sm:text-4xl">
                Doc tin thi truong, quy hoach va kinh nghiem mua nha
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
                Noi dung duoc lay tu bang articles. Trang uu tien du lieu that,
                dong thoi co noi dung mau khi backend chua san sang.
              </p>
            </div>

            <form
              onSubmit={submitSearch}
              className="rounded-lg border border-border bg-background p-3 shadow-sm"
            >
              <label className="mb-2 block text-xs font-semibold text-muted-foreground">
                Tim tin tuc
              </label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Search
                    size={16}
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                  />
                  <input
                    value={draftSearch}
                    onChange={(event) => setDraftSearch(event.target.value)}
                    placeholder="Nhap tu khoa thi truong, quy hoach..."
                    className="w-full rounded-md border border-border bg-card py-2.5 pl-9 pr-3 text-sm outline-none transition-colors focus:border-primary"
                  />
                </div>
                <button
                  type="submit"
                  className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary-hover"
                >
                  <Search size={15} />
                  Tim
                </button>
              </div>
            </form>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-6">
        <div className="mb-5 flex flex-col gap-3 rounded-lg border border-border bg-card p-4 shadow-sm lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-2">
            {CATEGORIES.map((category) => {
              const Icon = category.icon;
              const active = (filters.category || "") === category.value;
              return (
                <button
                  key={category.value || "all"}
                  onClick={() =>
                    setFilters((current) => ({
                      ...current,
                      category: category.value || undefined,
                      page: 1,
                    }))
                  }
                  className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    active
                      ? "bg-primary text-primary-foreground"
                      : "bg-background text-foreground hover:bg-muted"
                  }`}
                >
                  <Icon size={15} />
                  {category.label}
                </button>
              );
            })}
          </div>

          <select
            value={filters.sort || "newest"}
            onChange={(event) =>
              setFilters((current) => ({ ...current, sort: event.target.value, page: 1 }))
            }
            className="rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
          >
            <option value="newest">Moi nhat</option>
            <option value="oldest">Cu nhat</option>
          </select>
        </div>

        <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
          <div>
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold text-foreground">Tin noi bat</h2>
                <p className="text-xs text-muted-foreground">
                  {usingFallback
                    ? "Dang hien thi du lieu mau"
                    : "Dang hien thi du lieu tu API"}
                </p>
              </div>
              {loading && (
                <span className="rounded-md bg-muted px-3 py-1 text-xs text-muted-foreground">
                  Dang tai...
                </span>
              )}
            </div>

            <article className="mb-5 rounded-lg border border-border bg-card p-5 shadow-sm">
              <div className="grid gap-5 md:grid-cols-[1fr_220px] md:items-center">
                <div>
                  <span className="inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-1 text-[11px] font-semibold text-primary">
                    <TrendingUp size={12} />
                    {categoryLabel(featured.category)}
                  </span>
                  <h2 className="mt-3 text-2xl font-extrabold leading-8 text-foreground">
                    {featured.title}
                  </h2>
                  <p className="mt-3 line-clamp-3 text-sm leading-6 text-muted-foreground">
                    {articleSummary(featured)}
                  </p>
                  <a
                    href={featured.url || `/tin-tuc?article=${featured.id}`}
                    target={featured.url ? "_blank" : undefined}
                    rel={featured.url ? "noreferrer" : undefined}
                    className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
                  >
                    Doc bai viet <ArrowRight size={14} />
                  </a>
                </div>
                <div className="rounded-lg bg-muted p-4">
                  <p className="text-xs font-semibold uppercase text-muted-foreground">
                    Nguon
                  </p>
                  <p className="mt-1 text-sm font-bold text-foreground">
                    {featured.source || "batdongsan.com"}
                  </p>
                  <p className="mt-4 text-xs font-semibold uppercase text-muted-foreground">
                    Ngay dang
                  </p>
                  <p className="mt-1 text-sm font-bold text-foreground">
                    {formatDate(featured.post_date)}
                  </p>
                </div>
              </div>
            </article>

            <div className="grid gap-4 md:grid-cols-2">
              {secondaryArticles.map((article) => (
                <ArticleCardItem key={article.id} article={article} />
              ))}
            </div>
          </div>

          <aside className="space-y-4">
            <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
              <h2 className="text-sm font-bold text-foreground">Chu de dang doc</h2>
              <div className="mt-3 space-y-2">
                {sourceStats.map(([category, count]) => (
                  <div
                    key={category}
                    className="flex items-center justify-between rounded-md bg-background px-3 py-2 text-sm"
                  >
                    <span>{category}</span>
                    <span className="text-xs text-muted-foreground">{count} bai</span>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
              <h2 className="text-sm font-bold text-foreground">Goc phan tich</h2>
              <div className="mt-3 space-y-3 text-sm leading-6 text-muted-foreground">
                <p>Theo doi bien dong gia, ha tang va thanh khoan theo khu vuc.</p>
                <p>Luu cac bai viet quan trong de hoi chatbot ve ngu canh dau tu.</p>
              </div>
            </section>
          </aside>
        </div>
      </section>
    </div>
  );
}
