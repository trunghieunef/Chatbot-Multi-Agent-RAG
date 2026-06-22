"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  Newspaper,
  Tag,
  UserRound,
} from "lucide-react";
import { getArticleDetail, getArticles, getProjects } from "@/lib/api";
import { formatDescription } from "@/lib/utils";
import type { ArticleCard, ArticleDetail, ProjectCard } from "@/lib/types";

function categoryLabel(category: string | null): string {
  const labels: Record<string, string> = {
    market: "Thị trường",
    guide: "Hướng dẫn",
    planning: "Quy hoạch",
    news: "Tin tức",
    legal: "Pháp lý",
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

function fieldLabel(value: string | number | null | undefined, fallback = "Đang cập nhật") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

export default function ArticleDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const invalidId = !Number.isFinite(id) || id <= 0;
  const [article, setArticle] = useState<ArticleDetail | null>(null);
  const [related, setRelated] = useState<ArticleCard[]>([]);
  const [projects, setProjects] = useState<ProjectCard[]>([]);
  const [loading, setLoading] = useState(!invalidId);

  useEffect(() => {
    if (invalidId) return;

    let cancelled = false;

    getArticleDetail(id)
      .then(async (data) => {
        if (cancelled) return;
        setArticle(data);

        const [articleList, projectList] = await Promise.all([
          getArticles({ category: data.category || undefined, limit: 5 }).catch(() => ({
            items: [],
            total: 0,
            page: 1,
            limit: 5,
            total_pages: 0,
          })),
          getProjects({ limit: 4 }).catch(() => ({
            items: [],
            total: 0,
            page: 1,
            limit: 4,
            total_pages: 0,
          })),
        ]);

        if (cancelled) return;
        setRelated(articleList.items.filter((item) => item.id !== data.id).slice(0, 4));
        setProjects(projectList.items.slice(0, 3));
      })
      .catch(() => {
        if (!cancelled) setArticle(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [id, invalidId]);

  const paragraphs = useMemo(() => {
    const content = article?.body || article?.summary || "";
    return formatDescription(content)
      .split(/\n+/)
      .map((line) => line.trim())
      .filter(Boolean);
  }, [article]);
  const imageUrls = article?.image_urls || [];

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8">
        <div className="mb-4 h-4 w-52 skeleton" />
        <div className="mb-4 h-8 w-4/5 skeleton" />
        <div className="mb-8 h-5 w-64 skeleton" />
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <div className="space-y-3">
            <div className="h-6 w-full skeleton" />
            <div className="h-6 w-11/12 skeleton" />
            <div className="h-6 w-10/12 skeleton" />
          </div>
          <div className="h-48 rounded-lg skeleton" />
        </div>
      </div>
    );
  }

  if (!article) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col items-center px-4 py-24 text-center">
        <Newspaper size={44} className="mb-4 text-muted-foreground" />
        <h1 className="text-xl font-bold text-foreground">Không tìm thấy bài viết</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Bài viết này có thể đã bị xóa hoặc chưa được đồng bộ từ hệ thống.
        </p>
        <Link
          href="/tin-tuc"
          className="mt-5 inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-semibold text-foreground hover:bg-muted"
        >
          <ArrowLeft size={15} />
          Quay lại tin tức
        </Link>
      </div>
    );
  }

  return (
    <div className="bg-background">
      <section className="border-b border-border bg-card">
        <div className="mx-auto max-w-7xl px-4 py-7">
          <nav className="mb-5 text-xs text-muted-foreground">
            <Link href="/" className="hover:text-primary">
              Trang chủ
            </Link>
            <span className="mx-1.5">/</span>
            <Link href="/tin-tuc" className="hover:text-primary">
              Tin tức
            </Link>
            <span className="mx-1.5">/</span>
            <span className="font-medium text-foreground">Chi tiết bài viết</span>
          </nav>

          <div className="max-w-4xl">
            <span className="inline-flex items-center gap-2 rounded-md bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
              <Newspaper size={14} />
              {categoryLabel(article.category)}
            </span>
            <h1 className="mt-4 text-3xl font-extrabold leading-tight text-foreground sm:text-4xl">
              {article.title}
            </h1>
            <div className="mt-4 flex flex-wrap gap-4 text-sm text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <CalendarDays size={15} className="text-primary" />
                Ngày đăng: {formatDate(article.post_date)}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <UserRound size={15} className="text-primary" />
                Nguồn: {fieldLabel(article.source, "Hệ thống tin tức")}
              </span>
            </div>
          </div>
        </div>
      </section>

      <main className="mx-auto grid max-w-7xl gap-6 px-4 py-7 lg:grid-cols-[1fr_320px]">
        <article className="min-w-0">
          <div
            className="mb-6 flex h-72 items-center justify-center overflow-hidden rounded-lg border border-border bg-muted bg-cover bg-center"
            style={
              article.primary_image_url
                ? { backgroundImage: `url(${article.primary_image_url})` }
                : undefined
            }
          >
            {!article.primary_image_url && (
              <Newspaper size={48} className="text-primary/50" />
            )}
          </div>

          {imageUrls.length > 1 && (
            <div className="mb-6 flex gap-2 overflow-x-auto">
              {imageUrls.slice(0, 8).map((imageUrl, index) => (
                <div
                  key={`${imageUrl}-${index}`}
                  className="h-16 w-24 shrink-0 rounded-md border border-border bg-muted bg-cover bg-center"
                  style={{ backgroundImage: `url(${imageUrl})` }}
                  aria-label={`Ảnh bài viết ${index + 1}`}
                />
              ))}
            </div>
          )}

          {article.summary && (
            <p className="mb-5 border-l-4 border-primary pl-4 text-lg font-semibold leading-8 text-foreground">
              {article.summary}
            </p>
          )}

          <div className="rounded-lg border border-border bg-card p-5 shadow-sm sm:p-7">
            <div className="prose prose-sm max-w-none text-foreground prose-p:leading-7">
              {paragraphs.length > 0 ? (
                paragraphs.map((paragraph, index) => (
                  <p key={`${paragraph.slice(0, 24)}-${index}`} className="mb-4 text-sm leading-7">
                    {paragraph}
                  </p>
                ))
              ) : (
                <p className="text-sm leading-7 text-muted-foreground">
                  Nội dung bài viết đang được cập nhật.
                </p>
              )}
            </div>

            {article.url && (
              <a
                href={article.url}
                target="_blank"
                rel="noreferrer"
                className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-primary hover:underline"
              >
                Xem nguồn bài viết <ArrowRight size={14} />
              </a>
            )}
          </div>
        </article>

        <aside className="space-y-4">
          <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
            <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
              <Tag size={15} className="text-primary" />
              Thông tin bài viết
            </h2>
            <div className="mt-4 space-y-3 text-sm">
              <div>
                <p className="text-xs text-muted-foreground">Chuyên mục</p>
                <p className="mt-1 font-semibold text-foreground">
                  {categoryLabel(article.category)}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Ngày đăng</p>
                <p className="mt-1 font-semibold text-foreground">
                  {formatDate(article.post_date)}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Nguồn</p>
                <p className="mt-1 font-semibold text-foreground">
                  {fieldLabel(article.source, "Hệ thống tin tức")}
                </p>
              </div>
            </div>
          </section>

          {related.length > 0 && (
            <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
              <h2 className="text-sm font-bold text-foreground">Bài viết liên quan</h2>
              <div className="mt-3 space-y-3">
                {related.map((item) => (
                  <Link
                    key={item.id}
                    href={`/tin-tuc/${item.id}`}
                    className="block rounded-md p-2 transition-colors hover:bg-muted"
                  >
                    <p className="line-clamp-2 text-sm font-semibold leading-5 text-foreground">
                      {item.title}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {formatDate(item.post_date)}
                    </p>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {projects.length > 0 && (
            <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
              <h2 className="text-sm font-bold text-foreground">Dự án nổi bật</h2>
              <div className="mt-3 space-y-2">
                {projects.map((project) => (
                  <Link
                    key={project.id}
                    href={`/du-an/${project.id}`}
                    className="block rounded-md p-2 transition-colors hover:bg-muted"
                  >
                    <p className="line-clamp-1 text-sm font-semibold text-foreground">
                      {project.name}
                    </p>
                    <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">
                      {fieldLabel(project.location)}
                    </p>
                  </Link>
                ))}
              </div>
            </section>
          )}
        </aside>
      </main>
    </div>
  );
}
