"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  BadgeCheck,
  Building2,
  Layers3,
  MapPin,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { getProjects } from "@/lib/api";
import type { ProjectCard, ProjectFilters } from "@/lib/types";

const FALLBACK_PROJECTS: ProjectCard[] = [
  {
    id: 9001,
    name: "The River District",
    slug: "the-river-district",
    developer: "Saigon Urban",
    location: "Thủ Đức, Hồ Chí Minh",
    district: "Thủ Đức",
    city: "Hồ Chí Minh",
    total_units: 1800,
    price_range: "4,2 - 9,8 tỷ",
    area_range: "48 - 126 m²",
    status: "selling",
    project_type: "Căn hộ",
    description:
      "Cụm căn hộ ven sông với tiện ích nội khu đầy đủ, kết nối nhanh tới trung tâm và khu công nghệ cao.",
    amenities: ["Hồ bơi", "Công viên", "Trung tâm thương mại"],
    url: null,
    created_at: null,
    updated_at: null,
  },
  {
    id: 9002,
    name: "West Lake Residence",
    slug: "west-lake-residence",
    developer: "Capital Homes",
    location: "Tây Hồ, Hà Nội",
    district: "Tây Hồ",
    city: "Hà Nội",
    total_units: 760,
    price_range: "6,5 - 18 tỷ",
    area_range: "62 - 180 m²",
    status: "upcoming",
    project_type: "Căn hộ cao cấp",
    description:
      "Dự án căn hộ cao cấp gần hồ Tây, tập trung vào không gian sống riêng tư và dịch vụ quản lý chuyên nghiệp.",
    amenities: ["Sky lounge", "Gym", "Khu trẻ em"],
    url: null,
    created_at: null,
    updated_at: null,
  },
  {
    id: 9003,
    name: "Green Valley Villas",
    slug: "green-valley-villas",
    developer: "EcoLand",
    location: "Đà Nẵng",
    district: "Ngũ Hành Sơn",
    city: "Đà Nẵng",
    total_units: 220,
    price_range: "12 - 35 tỷ",
    area_range: "180 - 420 m²",
    status: "completed",
    project_type: "Biệt thự",
    description:
      "Khu biệt thự thấp tầng gần biển, phù hợp nhu cầu nghỉ dưỡng dài hạn và khai thác cho thuê.",
    amenities: ["Bảo vệ 24/7", "Clubhouse", "Đường dạo bộ"],
    url: null,
    created_at: null,
    updated_at: null,
  },
];

const CITY_OPTIONS = ["", "Hồ Chí Minh", "Hà Nội", "Đà Nẵng", "Quảng Ninh"];
const TYPE_OPTIONS = ["", "Căn hộ", "Biệt thự", "Shophouse", "Nhà phố"];
const STATUS_OPTIONS = ["", "selling", "upcoming", "completed"];

function statusLabel(status: string | null): string {
  const labels: Record<string, string> = {
    selling: "Đang mở bán",
    upcoming: "Sắp ra mắt",
    completed: "Đã bàn giao",
  };
  return status ? labels[status] || status : "Đang cập nhật";
}

function fieldLabel(value: string | null | undefined, fallback = "Đang cập nhật") {
  return value && value.trim() ? value : fallback;
}

function ProjectCardItem({ project }: { project: ProjectCard }) {
  const href = project.url || `/du-an?project=${project.slug || project.id}`;

  return (
    <article className="group rounded-lg border border-border bg-card p-4 shadow-sm transition-all hover:border-primary/40 hover:shadow-md">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <span className="mb-2 inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-1 text-[11px] font-semibold text-primary">
            <BadgeCheck size={12} />
            {statusLabel(project.status)}
          </span>
          <h2 className="line-clamp-2 text-base font-bold text-foreground">
            {project.name}
          </h2>
        </div>
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted text-primary">
          <Building2 size={20} />
        </div>
      </div>

      <div className="space-y-2 text-sm text-muted-foreground">
        <p className="flex items-start gap-2">
          <MapPin size={15} className="mt-0.5 shrink-0 text-primary" />
          <span className="line-clamp-1">{fieldLabel(project.location)}</span>
        </p>
        <p className="flex items-center gap-2">
          <Layers3 size={15} className="shrink-0 text-primary" />
          <span>{fieldLabel(project.project_type)}</span>
        </p>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-md bg-muted p-2">
          <p className="text-muted-foreground">Giá</p>
          <p className="mt-1 font-semibold text-foreground">
            {fieldLabel(project.price_range)}
          </p>
        </div>
        <div className="rounded-md bg-muted p-2">
          <p className="text-muted-foreground">Diện tích</p>
          <p className="mt-1 font-semibold text-foreground">
            {fieldLabel(project.area_range)}
          </p>
        </div>
      </div>

      <p className="mt-4 line-clamp-3 text-sm leading-6 text-muted-foreground">
        {fieldLabel(project.description, "Thông tin dự án đang được cập nhật.")}
      </p>

      {project.amenities.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {project.amenities.slice(0, 3).map((amenity) => (
            <span
              key={amenity}
              className="rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground"
            >
              {amenity}
            </span>
          ))}
        </div>
      )}

      <a
        href={href}
        target={project.url ? "_blank" : undefined}
        rel={project.url ? "noreferrer" : undefined}
        className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
      >
        Xem dự án <ArrowRight size={14} />
      </a>
    </article>
  );
}

export default function ProjectsPage() {
  const [filters, setFilters] = useState<ProjectFilters>({
    sort: "newest",
    limit: 12,
  });
  const [draftSearch, setDraftSearch] = useState("");
  const [projects, setProjects] = useState<ProjectCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [usingFallback, setUsingFallback] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getProjects(filters)
      .then((data) => {
        if (cancelled) return;
        setProjects(data.items.length > 0 ? data.items : FALLBACK_PROJECTS);
        setUsingFallback(data.items.length === 0);
      })
      .catch(() => {
        if (cancelled) return;
        setProjects(FALLBACK_PROJECTS);
        setUsingFallback(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [filters]);

  const highlightedCities = useMemo(() => {
    const counts = new Map<string, number>();
    projects.forEach((project) => {
      if (project.city) counts.set(project.city, (counts.get(project.city) || 0) + 1);
    });
    return Array.from(counts.entries()).slice(0, 5);
  }, [projects]);

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
            <span className="font-medium text-foreground">Dự án</span>
          </nav>

          <div className="grid gap-6 lg:grid-cols-[1.25fr_0.75fr] lg:items-end">
            <div>
              <span className="inline-flex items-center gap-2 rounded-md bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                <Building2 size={14} />
                Dự án bất động sản
              </span>
              <h1 className="mt-4 text-3xl font-extrabold text-foreground sm:text-4xl">
                Tìm dự án theo khu vực, loại hình và trạng thái
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
                Cập nhật danh sách dự án từ dữ liệu crawler. Khi dữ liệu chưa sẵn
                sàng, trang vẫn hiển thị bộ mẫu để giữ trải nghiệm duyệt nội dung.
              </p>
            </div>

            <form
              onSubmit={submitSearch}
              className="rounded-lg border border-border bg-background p-3 shadow-sm"
            >
              <label className="mb-2 block text-xs font-semibold text-muted-foreground">
                Tìm kiếm dự án
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
                    placeholder="Nhập tên dự án, chủ đầu tư, khu vực..."
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
        <div className="mb-5 rounded-lg border border-border bg-card p-4 shadow-sm">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
            <SlidersHorizontal size={16} className="text-primary" />
            Bộ lọc dự án
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <select
              value={filters.city || ""}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  city: event.target.value || undefined,
                  page: 1,
                }))
              }
              className="rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
            >
              {CITY_OPTIONS.map((city) => (
                <option key={city || "all"} value={city}>
                  {city || "Tất cả thành phố"}
                </option>
              ))}
            </select>

            <select
              value={filters.project_type || ""}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  project_type: event.target.value || undefined,
                  page: 1,
                }))
              }
              className="rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
            >
              {TYPE_OPTIONS.map((type) => (
                <option key={type || "all"} value={type}>
                  {type || "Tất cả loại hình"}
                </option>
              ))}
            </select>

            <select
              value={filters.status || ""}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  status: event.target.value || undefined,
                  page: 1,
                }))
              }
              className="rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
            >
              {STATUS_OPTIONS.map((status) => (
                <option key={status || "all"} value={status}>
                  {status ? statusLabel(status) : "Tất cả trạng thái"}
                </option>
              ))}
            </select>

            <select
              value={filters.sort || "newest"}
              onChange={(event) =>
                setFilters((current) => ({ ...current, sort: event.target.value, page: 1 }))
              }
              className="rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
            >
              <option value="newest">Mới nhất</option>
              <option value="name_asc">Tên A-Z</option>
              <option value="name_desc">Tên Z-A</option>
            </select>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
          <div>
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold text-foreground">
                  Danh sách dự án
                </h2>
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

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {projects.map((project) => (
                <ProjectCardItem key={project.id} project={project} />
              ))}
            </div>
          </div>

          <aside className="space-y-4">
            <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
              <h2 className="text-sm font-bold text-foreground">Khu vực nổi bật</h2>
              <div className="mt-3 space-y-2">
                {highlightedCities.map(([city, count]) => (
                  <button
                    key={city}
                    onClick={() =>
                      setFilters((current) => ({ ...current, city, page: 1 }))
                    }
                    className="flex w-full items-center justify-between rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-muted"
                  >
                    <span>{city}</span>
                    <span className="text-xs text-muted-foreground">{count} dự án</span>
                  </button>
                ))}
              </div>
            </section>

            <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
              <h2 className="text-sm font-bold text-foreground">Gợi ý tìm kiếm</h2>
              <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                <p>Căn hộ đang mở bán tại thành phố lớn.</p>
                <p>Dự án đã bàn giao phù hợp khai thác cho thuê.</p>
                <p>Shophouse và biệt thự cho nhà đầu tư dài hạn.</p>
              </div>
            </section>
          </aside>
        </div>
      </section>
    </div>
  );
}
