"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  Ruler, Bed, Bath, Layers, Compass, Scale, Sofa,
  MapPin, Phone, User, Calendar, ArrowLeft, Share2,
} from "lucide-react";
import { getListingDetail, getSimilarListings } from "@/lib/api";
import ListingCard from "@/components/listing/ListingCard";
import type { ListingDetail, ListingCard as ListingCardType } from "@/lib/types";

interface SpecItem {
  icon: React.ReactNode;
  label: string;
  value: string | number | null | undefined;
}

export default function ListingDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const [listing, setListing] = useState<ListingDetail | null>(null);
  const [similar, setSimilar] = useState<ListingCardType[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getListingDetail(id)
      .then((data) => {
        setListing(data);
        return getSimilarListings(id, 4);
      })
      .then(setSimilar)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-8">
        <div className="h-6 w-40 skeleton mb-4" />
        <div className="h-64 skeleton rounded-2xl mb-6" />
        <div className="space-y-3">
          <div className="h-8 w-3/4 skeleton" />
          <div className="h-5 w-1/3 skeleton" />
          <div className="h-24 skeleton" />
        </div>
      </div>
    );
  }

  if (!listing) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <span className="text-5xl mb-4">🏚️</span>
        <h2 className="text-xl font-bold text-foreground">
          Không tìm thấy tin đăng
        </h2>
        <p className="text-sm text-muted-foreground mt-1 mb-4">
          Tin đăng này có thể đã bị xóa hoặc không tồn tại.
        </p>
        <Link href="/nha-dat-ban" className="text-sm text-primary hover:underline">
          ← Quay lại danh sách
        </Link>
      </div>
    );
  }

  const specs: SpecItem[] = [
    { icon: <Ruler size={16} />, label: "Diện tích", value: listing.area_text },
    { icon: <Bed size={16} />, label: "Phòng ngủ", value: listing.bedrooms },
    { icon: <Bath size={16} />, label: "Phòng tắm", value: listing.bathrooms },
    { icon: <Layers size={16} />, label: "Số tầng", value: listing.floors },
    { icon: <Compass size={16} />, label: "Hướng nhà", value: listing.direction },
    { icon: <Compass size={16} />, label: "Hướng ban công", value: listing.balcony_direction },
    { icon: <Scale size={16} />, label: "Pháp lý", value: listing.legal_status },
    { icon: <Sofa size={16} />, label: "Nội thất", value: listing.furniture },
  ].filter((s) => s.value != null && s.value !== "");

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      {/* Breadcrumb */}
      <nav className="mb-4 text-xs text-muted-foreground">
        <Link href="/" className="hover:text-primary">Trang chủ</Link>
        <span className="mx-1.5">›</span>
        <Link href="/nha-dat-ban" className="hover:text-primary">Nhà đất bán</Link>
        <span className="mx-1.5">›</span>
        <span className="text-foreground font-medium truncate">
          {listing.title?.slice(0, 40)}...
        </span>
      </nav>

      {/* Image placeholder */}
      <div className="mb-6 h-64 sm:h-80 rounded-2xl bg-gradient-to-br from-primary/10 via-accent-light/10 to-muted flex items-center justify-center relative overflow-hidden">
        <span className="text-7xl opacity-20">🏠</span>
        {listing.badge && (
          <span className="absolute top-4 left-4 rounded-lg bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground">
            {listing.badge}
          </span>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Title + Price */}
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-foreground leading-snug mb-2">
              {listing.title}
            </h1>
            {listing.address && (
              <p className="flex items-center gap-1.5 text-sm text-muted-foreground mb-3">
                <MapPin size={14} className="text-accent-light shrink-0" />
                {listing.address}
              </p>
            )}
            <div className="flex items-baseline gap-3">
              <span className="text-2xl font-bold text-primary">
                {listing.price_text || "Liên hệ"}
              </span>
              {listing.price_per_m2_text && (
                <span className="text-sm text-muted-foreground">
                  · {listing.price_per_m2_text}
                </span>
              )}
            </div>
          </div>

          {/* Specs Grid */}
          {specs.length > 0 && (
            <div className="rounded-xl border border-border bg-card p-5">
              <h2 className="text-sm font-bold text-foreground mb-4">
                Thông tin chi tiết
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {specs.map((s, i) => (
                  <div key={i} className="flex items-start gap-2.5">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                      {s.icon}
                    </div>
                    <div>
                      <p className="text-[11px] text-muted-foreground">{s.label}</p>
                      <p className="text-sm font-semibold text-foreground">{s.value}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Description */}
          {listing.description && (
            <div className="rounded-xl border border-border bg-card p-5">
              <h2 className="text-sm font-bold text-foreground mb-3">
                Mô tả chi tiết
              </h2>
              <div className="text-sm text-foreground/80 leading-relaxed whitespace-pre-line">
                {listing.description}
              </div>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Contact Card */}
          <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
            <h3 className="text-sm font-bold text-foreground mb-4">
              Thông tin liên hệ
            </h3>
            {listing.contact_name && (
              <p className="flex items-center gap-2 text-sm text-foreground mb-2">
                <User size={14} className="text-muted-foreground" />
                {listing.contact_name}
              </p>
            )}
            {listing.contact_phone && (
              <a
                href={`tel:${listing.contact_phone}`}
                className="flex items-center gap-2 rounded-lg bg-success px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-success/90 mb-3"
              >
                <Phone size={16} />
                {listing.contact_phone}
              </a>
            )}
            {listing.post_date && (
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <Calendar size={12} />
                Ngày đăng: {listing.post_date}
              </p>
            )}
          </div>

          {/* Actions */}
          <div className="flex gap-2">
            <Link
              href="/nha-dat-ban"
              className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-border py-2.5 text-sm font-medium text-foreground hover:bg-muted transition-colors"
            >
              <ArrowLeft size={14} /> Quay lại
            </Link>
            <button className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-border py-2.5 text-sm font-medium text-foreground hover:bg-muted transition-colors">
              <Share2 size={14} /> Chia sẻ
            </button>
          </div>
        </div>
      </div>

      {/* Similar listings */}
      {similar.length > 0 && (
        <section className="mt-12">
          <h2 className="text-lg font-bold text-foreground mb-4">
            Tin đăng tương tự
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {similar.map((l, i) => (
              <ListingCard key={l.id} listing={l} index={i} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
