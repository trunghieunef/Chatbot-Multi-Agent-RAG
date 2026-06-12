import Link from "next/link";
import {
  Bed,
  Bath,
  Ruler,
  MapPin,
  Calendar,
  User,
  ArrowUpRight,
} from "lucide-react";
import type { ListingCard as ListingCardType } from "@/lib/types";

interface Props {
  listing: ListingCardType;
  index?: number;
}

export default function ListingCard({ listing, index = 0 }: Props) {
  return (
    <Link
      href={`/nha-dat-ban/${listing.id}`}
      className="group flex flex-col rounded-xl border border-border bg-card overflow-hidden shadow-sm transition-all duration-300 hover:shadow-lg hover:-translate-y-1 animate-fade-in-up"
      style={{ animationDelay: `${index * 60}ms` }}
    >
      <div className="relative h-44 bg-gradient-to-br from-primary/10 via-accent-light/10 to-muted flex items-center justify-center overflow-hidden">
        {listing.primary_image_url ? (
          <img
            src={listing.primary_image_url}
            alt={listing.title || "Listing image"}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <span className="text-4xl opacity-30">🏠</span>
        )}
        {listing.badge && (
          <span className="absolute top-2 left-2 rounded-md bg-primary px-2 py-0.5 text-[10px] font-semibold text-primary-foreground uppercase tracking-wide">
            {listing.badge}
          </span>
        )}
        <span className="absolute top-2 right-2 rounded-full bg-card/80 backdrop-blur p-1.5 opacity-0 transition-opacity group-hover:opacity-100">
          <ArrowUpRight size={14} className="text-primary" />
        </span>
      </div>

      {/* Content */}
      <div className="flex flex-1 flex-col p-4 gap-2">
        <h3 className="text-sm font-semibold leading-snug text-card-foreground line-clamp-2 group-hover:text-primary transition-colors">
          {listing.title || "Chưa có tiêu đề"}
        </h3>

        {/* Price */}
        <div className="flex items-baseline gap-2">
          <span className="text-base font-bold text-primary">
            {listing.price_text || "Liên hệ"}
          </span>
          {listing.price_per_m2_text && (
            <span className="text-[11px] text-muted-foreground">
              · {listing.price_per_m2_text}
            </span>
          )}
        </div>

        {/* Specs */}
        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
          {listing.area_text && (
            <span className="flex items-center gap-1">
              <Ruler size={12} /> {listing.area_text}
            </span>
          )}
          {listing.bedrooms != null && (
            <span className="flex items-center gap-1">
              <Bed size={12} /> {listing.bedrooms} PN
            </span>
          )}
          {listing.bathrooms != null && (
            <span className="flex items-center gap-1">
              <Bath size={12} /> {listing.bathrooms} WC
            </span>
          )}
        </div>

        {/* Location */}
        {(listing.district || listing.city) && (
          <p className="flex items-center gap-1 text-xs text-muted-foreground mt-auto pt-2">
            <MapPin size={12} className="text-accent-light shrink-0" />
            <span className="truncate">
              {[listing.district, listing.city].filter(Boolean).join(", ")}
            </span>
          </p>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border pt-2 mt-1 text-[11px] text-muted-foreground">
          {listing.contact_name && (
            <span className="flex items-center gap-1 truncate">
              <User size={11} /> {listing.contact_name}
            </span>
          )}
          {listing.post_date && (
            <span className="flex items-center gap-1 shrink-0">
              <Calendar size={11} /> {listing.post_date}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}
