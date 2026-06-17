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
    location: "Thu Duc, Ho Chi Minh",
    district: "Thu Duc",
    city: "Ho Chi Minh",
    total_units: 1800,
    price_range: "4.2 - 9.8 ty",
    area_range: "48 - 126 m2",
    status: "selling",
    project_type: "Can ho",
    description:
      "Cum can ho ven song voi tien ich noi khu day du, ket noi nhanh toi trung tam va khu cong nghe cao.",
    amenities: ["Ho boi", "Cong vien", "Trung tam thuong mai"],
    url: null,
    created_at: null,
    updated_at: null,
  },
  {
    id: 9002,
    name: "West Lake Residence",
    slug: "west-lake-residence",
    developer: "Capital Homes",
    location: "Tay Ho, Ha Noi",
    district: "Tay Ho",
    city: "Ha Noi",
    total_units: 760,
    price_range: "6.5 - 18 ty",
    area_range: "62 - 180 m2",
    status: "upcoming",
    project_type: "Can ho cao cap",
    description:
      "Du an can ho cao cap gan ho Tay, tap trung vao khong gian song rieng tu va dich vu quan ly chuyen nghiep.",
    amenities: ["Sky lounge", "Gym", "Khu tre em"],
    url: null,
    created_at: null,
    updated_at: null,
  },
  {
    id: 9003,
    name: "Green Valley Villas",
    slug: "green-valley-villas",
    developer: "EcoLand",
    location: "Da Nang",
    district: "Ngu Hanh Son",
    city: "Da Nang",
    total_units: 220,
    price_range: "12 - 35 ty",
    area_range: "180 - 420 m2",
    status: "completed",
    project_type: "Biet thu",
    description:
      "Khu biet thu thap tang gan bien, phu hop nhu cau nghi duong dai han va khai thac cho thue.",
    amenities: ["Bao ve 24/7", "Clubhouse", "Duong dao bo"],
    url: null,
    created_at: null,
    updated_at: null,
  },
];

const CITY_OPTIONS = ["", "Ho Chi Minh", "Ha Noi", "Da Nang", "Quang Ninh"];
const TYPE_OPTIONS = ["", "Can ho", "Biet thu", "Shophouse", "Nha pho"];
const STATUS_OPTIONS = ["", "selling", "upcoming", "completed"];

function statusLabel(status: string | null): string {
  const labels: Record<string, string> = {
    selling: "Dang mo ban",
    upcoming: "Sap ra mat",
    completed: "Da ban giao",
  };
  return status ? labels[status] || status : "Dang cap nhat";
}

function fieldLabel(value: string | null | undefined, fallback = "Dang cap nhat") {
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
          <p className="text-muted-foreground">Gia</p>
          <p className="mt-1 font-semibold text-foreground">
            {fieldLabel(project.price_range)}
          </p>
        </div>
        <div className="rounded-md bg-muted p-2">
          <p className="text-muted-foreground">Dien tich</p>
          <p className="mt-1 font-semibold text-foreground">
            {fieldLabel(project.area_range)}
          </p>
        </div>
      </div>

      <p className="mt-4 line-clamp-3 text-sm leading-6 text-muted-foreground">
        {fieldLabel(project.description, "Thong tin du an dang duoc cap nhat.")}
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
        Xem du an <ArrowRight size={14} />
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
              Trang chu
            </Link>
            <span className="mx-1.5">/</span>
            <span className="font-medium text-foreground">Du an</span>
          </nav>

          <div className="grid gap-6 lg:grid-cols-[1.25fr_0.75fr] lg:items-end">
            <div>
              <span className="inline-flex items-center gap-2 rounded-md bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                <Building2 size={14} />
                Du an bat dong san
              </span>
              <h1 className="mt-4 text-3xl font-extrabold text-foreground sm:text-4xl">
                Tim du an theo khu vuc, loai hinh va trang thai
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
                Cap nhat danh sach du an tu du lieu crawler. Khi du lieu chua san
                sang, trang van hien thi bo mau de giu trai nghiem duyet noi dung.
              </p>
            </div>

            <form
              onSubmit={submitSearch}
              className="rounded-lg border border-border bg-background p-3 shadow-sm"
            >
              <label className="mb-2 block text-xs font-semibold text-muted-foreground">
                Tim kiem du an
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
                    placeholder="Nhap ten du an, chu dau tu, khu vuc..."
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
        <div className="mb-5 rounded-lg border border-border bg-card p-4 shadow-sm">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
            <SlidersHorizontal size={16} className="text-primary" />
            Bo loc du an
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
                  {city || "Tat ca thanh pho"}
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
                  {type || "Tat ca loai hinh"}
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
                  {status ? statusLabel(status) : "Tat ca trang thai"}
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
              <option value="newest">Moi nhat</option>
              <option value="name_asc">Ten A-Z</option>
              <option value="name_desc">Ten Z-A</option>
            </select>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
          <div>
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold text-foreground">
                  Danh sach du an
                </h2>
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

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {projects.map((project) => (
                <ProjectCardItem key={project.id} project={project} />
              ))}
            </div>
          </div>

          <aside className="space-y-4">
            <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
              <h2 className="text-sm font-bold text-foreground">Khu vuc noi bat</h2>
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
                    <span className="text-xs text-muted-foreground">{count} du an</span>
                  </button>
                ))}
              </div>
            </section>

            <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
              <h2 className="text-sm font-bold text-foreground">Goi y tim kiem</h2>
              <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                <p>Can ho dang mo ban tai thanh pho lon.</p>
                <p>Du an da ban giao phu hop khai thac cho thue.</p>
                <p>Shophouse va biet thu cho nha dau tu dai han.</p>
              </div>
            </section>
          </aside>
        </div>
      </section>
    </div>
  );
}
