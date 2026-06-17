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
    title: "Thị trường nhà ở đô thị lớn tiếp tục phân hóa",
    body: null,
    summary:
      "Người mua ưu tiên sản phẩm có pháp lý rõ, tiện ích hoàn thiện và khả năng khai thác cho thuê ổn định.",
    category: "market",
    source: "batdongsan.com",
    post_date: "2026-06-15",
    url: null,
    created_at: null,
    updated_at: null,
  },
  {
    id: 8002,
    title: "Kinh nghiệm đọc thông tin quy hoạch trước khi xuống tiền",
    body: null,
    summary:
      "Kiểm tra quy hoạch, hạ tầng và lộ trình pháp lý giúp nhà đầu tư giảm rủi ro khi mua bất động sản.",
    category: "guide",
    source: "batdongsan.com",
    post_date: "2026-06-12",
    url: null,
    created_at: null,
    updated_at: null,
  },
  {
    id: 8003,
    title: "Hạ tầng mới tạo lực đẩy cho khu Đông",
    body: null,
    summary:
      "Các tuyến vành đai, metro và trục kết nối liên vùng tiếp tục là biến số quan trọng của giá nhà đất.",
    category: "planning",
    source: "batdongsan.com",
    post_date: "2026-06-09",
    url: null,
    created_at: null,
    updated_at: null,
  },
  {
    id: 8004,
    title: "Căn hộ vừa túi tiền vẫn giữ thanh khoản tốt",
    body: null,
    summary:
      "Phân khúc có tổng giá hợp lý, vị trí gần việc làm và tiện ích cơ bản vẫn được người mua thực sự quan tâm.",
    category: "news",
    source: "batdongsan.com",
    post_date: "2026-06-05",
    url: null,
    created_at: null,
    updated_at: null,
  },
];

const CATEGORIES = [
  { value: "", label: "Tất cả", icon: Newspaper },
  { value: "market", label: "Thị trường", icon: TrendingUp },
  { value: "guide", label: "Hướng dẫn", icon: BookOpen },
  { value: "planning", label: "Quy hoạch", icon: CalendarDays },
];

function categoryLabel(category: string | null): string {
  const labels: Record<string, string> = {
    market: "Thị trường",
    guide: "Hướng dẫn",
    planning: "Quy hoạch",
    news: "Tin tức",
  };
  return category ? labels[category] || category : "Tin tức";
}

function formatDate(value: string | null): string {
  if (!value) return "Mới cập nhật";
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
    "Nội dung bài viết đang được cập nhật từ hệ thống crawl tin tức."
  );
}

function ArticleCardItem({ article }: { article: ArticleCard }) {
  const href = `/tin-tuc/${article.id}`;

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
        <Link
          href={href}
          className="inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
        >
          Đọc tiếp <ArrowRight size={14} />
        </Link>
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
              Trang chủ
            </Link>
            <span className="mx-1.5">/</span>
            <span className="font-medium text-foreground">Tin tức</span>
          </nav>

          <div className="grid gap-6 lg:grid-cols-[1fr_360px] lg:items-end">
            <div>
              <span className="inline-flex items-center gap-2 rounded-md bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                <Newspaper size={14} />
                Tin tức bất động sản
              </span>
              <h1 className="mt-4 text-3xl font-extrabold text-foreground sm:text-4xl">
                Đọc tin thị trường, quy hoạch và kinh nghiệm mua nhà
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
                Nội dung được lấy từ bảng articles. Trang ưu tiên dữ liệu thật,
                đồng thời có nội dung mẫu khi backend chưa sẵn sàng.
              </p>
            </div>

            <form
              onSubmit={submitSearch}
              className="rounded-lg border border-border bg-background p-3 shadow-sm"
            >
              <label className="mb-2 block text-xs font-semibold text-muted-foreground">
                Tìm tin tức
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
                    placeholder="Nhập từ khóa thị trường, quy hoạch..."
                    className="w-full rounded-md border border-border bg-card py-2.5 pl-9 pr-3 text-sm outline-none transition-colors focus:border-primary"
                  />
                </div>
                <button
                  type="submit"
                  className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary-hover"
                >
                  <Search size={15} />
                  Tìm
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
            <option value="newest">Mới nhất</option>
            <option value="oldest">Cũ nhất</option>
          </select>
        </div>

        <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
          <div>
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold text-foreground">Tin nổi bật</h2>
                <p className="text-xs text-muted-foreground">
                  {usingFallback
                    ? "Đang hiển thị dữ liệu mẫu"
                    : "Đang hiển thị dữ liệu từ API"}
                </p>
              </div>
              {loading && (
                <span className="rounded-md bg-muted px-3 py-1 text-xs text-muted-foreground">
                  Đang tải...
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
                  <Link
                    href={`/tin-tuc/${featured.id}`}
                    className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
                  >
                    Đọc bài viết <ArrowRight size={14} />
                  </Link>
                </div>
                <div className="rounded-lg bg-muted p-4">
                  <p className="text-xs font-semibold uppercase text-muted-foreground">
                    Nguồn
                  </p>
                  <p className="mt-1 text-sm font-bold text-foreground">
                    {featured.source || "batdongsan.com"}
                  </p>
                  <p className="mt-4 text-xs font-semibold uppercase text-muted-foreground">
                    Ngày đăng
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
              <h2 className="text-sm font-bold text-foreground">Chủ đề đang đọc</h2>
              <div className="mt-3 space-y-2">
                {sourceStats.map(([category, count]) => (
                  <div
                    key={category}
                    className="flex items-center justify-between rounded-md bg-background px-3 py-2 text-sm"
                  >
                    <span>{category}</span>
                    <span className="text-xs text-muted-foreground">{count} bài</span>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
              <h2 className="text-sm font-bold text-foreground">Góc phân tích</h2>
              <div className="mt-3 space-y-3 text-sm leading-6 text-muted-foreground">
                <p>Theo dõi biến động giá, hạ tầng và thanh khoản theo khu vực.</p>
                <p>Lưu các bài viết quan trọng để hỏi chatbot về ngữ cảnh đầu tư.</p>
              </div>
            </section>
          </aside>
        </div>
      </section>
    </div>
  );
}
