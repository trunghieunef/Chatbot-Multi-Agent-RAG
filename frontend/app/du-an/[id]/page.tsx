"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  BadgeCheck,
  Building2,
  CheckCircle2,
  Home,
  Layers3,
  MapPin,
  Phone,
  Ruler,
} from "lucide-react";
import { getProjectDetail, getProjects } from "@/lib/api";
import { formatDescription } from "@/lib/utils";
import type { ProjectCard, ProjectDetail } from "@/lib/types";

function statusLabel(status: string | null): string {
  const labels: Record<string, string> = {
    selling: "Đang mở bán",
    upcoming: "Sắp ra mắt",
    completed: "Đã bàn giao",
  };
  return status ? labels[status] || status : "Đang cập nhật";
}

function fieldLabel(value: string | number | null | undefined, fallback = "Đang cập nhật") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function compactLocation(project: ProjectDetail): string {
  return [project.district, project.city].filter(Boolean).join(", ") || fieldLabel(project.location);
}

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const invalidId = !Number.isFinite(id) || id <= 0;
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [related, setRelated] = useState<ProjectCard[]>([]);
  const [loading, setLoading] = useState(!invalidId);
  const [selectedImageIndex, setSelectedImageIndex] = useState(0);

  useEffect(() => {
    if (invalidId) return;

    let cancelled = false;

    getProjectDetail(id)
      .then(async (data) => {
        if (cancelled) return;
        setSelectedImageIndex(0);
        setProject(data);

        const relatedProjects = await getProjects({
          city: data.city || undefined,
          project_type: data.project_type || undefined,
          limit: 4,
        }).catch(() => ({
          items: [],
          total: 0,
          page: 1,
          limit: 4,
          total_pages: 0,
        }));

        if (cancelled) return;
        setRelated(relatedProjects.items.filter((item) => item.id !== data.id).slice(0, 3));
      })
      .catch(() => {
        if (!cancelled) setProject(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [id, invalidId]);

  const facts = useMemo(() => {
    if (!project) return [];
    return [
      { icon: <Layers3 size={17} />, label: "Loại hình", value: project.project_type },
      { icon: <MapPin size={17} />, label: "Khu vực", value: compactLocation(project) },
      { icon: <Ruler size={17} />, label: "Diện tích", value: project.area_range },
      { icon: <Home size={17} />, label: "Số căn", value: project.total_units },
    ].filter((item) => item.value !== null && item.value !== undefined && item.value !== "");
  }, [project]);

  const descriptionParagraphs = useMemo(() => {
    const content = formatDescription(project?.description);
    return content
      .split(/\n+/)
      .map((line) => line.trim())
      .filter(Boolean);
  }, [project]);
  const imageUrls = project?.image_urls || [];
  const selectedImageUrl = imageUrls[selectedImageIndex] || project?.primary_image_url;

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8">
        <div className="mb-4 h-4 w-52 skeleton" />
        <div className="mb-4 h-10 w-3/4 skeleton" />
        <div className="mb-6 h-5 w-80 skeleton" />
        <div className="mb-6 h-72 rounded-lg skeleton" />
        <div className="grid gap-4 sm:grid-cols-4">
          <div className="h-24 rounded-lg skeleton" />
          <div className="h-24 rounded-lg skeleton" />
          <div className="h-24 rounded-lg skeleton" />
          <div className="h-24 rounded-lg skeleton" />
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col items-center px-4 py-24 text-center">
        <Building2 size={44} className="mb-4 text-muted-foreground" />
        <h1 className="text-xl font-bold text-foreground">Không tìm thấy dự án</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Dự án này có thể chưa được đồng bộ hoặc đã bị gỡ khỏi hệ thống.
        </p>
        <Link
          href="/du-an"
          className="mt-5 inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-semibold text-foreground hover:bg-muted"
        >
          <ArrowLeft size={15} />
          Quay lại dự án
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
            <Link href="/du-an" className="hover:text-primary">
              Dự án
            </Link>
            <span className="mx-1.5">/</span>
            <span className="font-medium text-foreground">Chi tiết dự án</span>
          </nav>

          <div className="grid gap-6 lg:grid-cols-[1fr_320px] lg:items-end">
            <div>
              <span className="inline-flex items-center gap-2 rounded-md bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                <BadgeCheck size={14} />
                {statusLabel(project.status)}
              </span>
              <h1 className="mt-4 text-3xl font-extrabold leading-tight text-foreground sm:text-4xl">
                {project.name}
              </h1>
              <p className="mt-3 flex items-start gap-2 text-sm text-muted-foreground">
                <MapPin size={16} className="mt-0.5 shrink-0 text-primary" />
                <span>{fieldLabel(project.location || compactLocation(project))}</span>
              </p>
            </div>

            <div className="rounded-lg border border-border bg-background p-4 shadow-sm">
              <p className="text-xs font-semibold uppercase text-muted-foreground">
                Giá tham khảo
              </p>
              <p className="mt-1 text-2xl font-extrabold text-primary">
                {fieldLabel(project.price_range, "Liên hệ")}
              </p>
              <p className="mt-3 text-xs font-semibold uppercase text-muted-foreground">
                Chủ đầu tư
              </p>
              <p className="mt-1 text-sm font-semibold text-foreground">
                {fieldLabel(project.developer)}
              </p>
            </div>
          </div>
        </div>
      </section>

      <main className="mx-auto max-w-7xl px-4 py-7">
        <div className="mb-6 overflow-hidden rounded-lg border border-border bg-card shadow-sm">
          <div
            className="flex min-h-[300px] items-center justify-center bg-[radial-gradient(circle_at_20%_20%,rgba(220,38,38,0.14),transparent_34%),linear-gradient(135deg,rgba(15,23,42,0.05),rgba(220,38,38,0.08))] bg-cover bg-center p-8"
            style={
              selectedImageUrl
                ? { backgroundImage: `linear-gradient(rgba(0,0,0,0.28), rgba(0,0,0,0.28)), url(${selectedImageUrl})` }
                : undefined
            }
          >
            <div
              className={`max-w-2xl text-center ${
                selectedImageUrl
                  ? "rounded-lg bg-black/50 p-5 text-white backdrop-blur"
                  : ""
              }`}
            >
              {!selectedImageUrl && (
                <Building2 size={58} className="mx-auto mb-4 text-primary" />
              )}
              <p className={`text-sm font-semibold uppercase ${selectedImageUrl ? "text-white/80" : "text-primary"}`}>
                Hồ sơ dự án
              </p>
              <h2 className={`mt-2 text-2xl font-extrabold ${selectedImageUrl ? "text-white" : "text-foreground"}`}>
                {project.name}
              </h2>
              <p className={`mt-3 text-sm leading-6 ${selectedImageUrl ? "text-white/80" : "text-muted-foreground"}`}>
                Thông tin tổng hợp từ dữ liệu dự án, được trình bày theo cấu trúc dễ quét
                cho nhu cầu so sánh và ra quyết định.
              </p>
            </div>
          </div>
          {imageUrls.length > 1 && (
            <div className="flex gap-2 overflow-x-auto border-t border-border bg-card p-3">
              {imageUrls.slice(0, 10).map((imageUrl, index) => (
                <button
                  key={`${imageUrl}-${index}`}
                  type="button"
                  onClick={() => setSelectedImageIndex(index)}
                  className={`h-16 w-24 shrink-0 rounded-md border-2 bg-muted bg-cover bg-center transition-colors ${
                    selectedImageIndex === index
                      ? "border-primary"
                      : "border-transparent hover:border-primary/50"
                  }`}
                  style={{ backgroundImage: `url(${imageUrl})` }}
                  aria-label={`Xem ảnh dự án ${index + 1}`}
                />
              ))}
            </div>
          )}
        </div>

        {facts.length > 0 && (
          <section className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {facts.map((item) => (
              <div
                key={item.label}
                className="rounded-lg border border-border bg-card p-4 shadow-sm"
              >
                <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
                  {item.icon}
                </div>
                <p className="text-xs text-muted-foreground">{item.label}</p>
                <p className="mt-1 font-bold text-foreground">{fieldLabel(item.value)}</p>
              </div>
            ))}
          </section>
        )}

        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <div className="space-y-6">
            <section id="tong-quan" className="rounded-lg border border-border bg-card p-5 shadow-sm">
              <h2 className="text-lg font-bold text-foreground">Tổng quan</h2>
              <div className="mt-3 space-y-4 text-sm leading-7 text-foreground/85">
                {descriptionParagraphs.length > 0 ? (
                  descriptionParagraphs.map((paragraph, index) => (
                    <p key={`${paragraph.slice(0, 24)}-${index}`}>{paragraph}</p>
                  ))
                ) : (
                  <p className="text-muted-foreground">
                    Thông tin tổng quan dự án đang được cập nhật.
                  </p>
                )}
              </div>
            </section>

            <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
              <h2 className="text-lg font-bold text-foreground">Thông tin chi tiết</h2>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {[
                  ["Tên dự án", project.name],
                  ["Chủ đầu tư", project.developer],
                  ["Loại hình", project.project_type],
                  ["Trạng thái", statusLabel(project.status)],
                  ["Khoảng giá", project.price_range],
                  ["Diện tích", project.area_range],
                  ["Quận/Huyện", project.district],
                  ["Thành phố", project.city],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-md bg-muted p-3">
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className="mt-1 text-sm font-semibold text-foreground">
                      {fieldLabel(value)}
                    </p>
                  </div>
                ))}
              </div>
            </section>

            {project.amenities.length > 0 && (
              <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
                <h2 className="text-lg font-bold text-foreground">Tiện ích</h2>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  {project.amenities.map((amenity) => (
                    <div
                      key={amenity}
                      className="flex items-center gap-3 rounded-md bg-muted p-3 text-sm font-medium text-foreground"
                    >
                      <CheckCircle2 size={17} className="shrink-0 text-primary" />
                      {amenity}
                    </div>
                  ))}
                </div>
              </section>
            )}

            <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
              <h2 className="text-lg font-bold text-foreground">Vị trí</h2>
              <div className="mt-4 rounded-lg border border-border bg-background p-4">
                <p className="flex items-start gap-2 text-sm font-semibold text-foreground">
                  <MapPin size={16} className="mt-0.5 shrink-0 text-primary" />
                  {fieldLabel(project.location || compactLocation(project))}
                </p>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  Bản đồ tương tác chưa được cấu hình cho dự án này. Bạn vẫn có thể dùng địa chỉ
                  để tra cứu thêm hoặc hỏi chatbot về khu vực lân cận.
                </p>
              </div>
            </section>

            {related.length > 0 && (
              <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
                <h2 className="text-lg font-bold text-foreground">Dự án liên quan</h2>
                <div className="mt-4 grid gap-3 md:grid-cols-3">
                  {related.map((item) => (
                    <Link
                      key={item.id}
                      href={`/du-an/${item.id}`}
                      className="rounded-lg border border-border p-3 transition-colors hover:border-primary/40 hover:bg-muted"
                    >
                      <p className="line-clamp-2 text-sm font-bold text-foreground">
                        {item.name}
                      </p>
                      <p className="mt-2 line-clamp-1 text-xs text-muted-foreground">
                        {fieldLabel(item.location)}
                      </p>
                      <p className="mt-3 text-xs font-semibold text-primary">
                        {fieldLabel(item.price_range, "Liên hệ")}
                      </p>
                    </Link>
                  ))}
                </div>
              </section>
            )}
          </div>

          <aside className="space-y-4">
            <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
              <h2 className="text-sm font-bold text-foreground">Tư vấn dự án</h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Nhận phân tích nhanh về giá, vị trí và phương án tài chính cho dự án này.
              </p>
              <a
                href="tel:0900000000"
                className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary-hover"
              >
                <Phone size={16} />
                Liên hệ tư vấn
              </a>
            </section>

            <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
              <h2 className="text-sm font-bold text-foreground">Điểm cần xem</h2>
              <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                <p>Pháp lý và tiến độ bàn giao.</p>
                <p>Mặt bằng, mật độ xây dựng và tiện ích nội khu.</p>
                <p>Giá so sánh với các dự án cùng khu vực.</p>
              </div>
            </section>
          </aside>
        </div>
      </main>
    </div>
  );
}
