"use client";

import { useEffect } from "react";
import { X, ChevronLeft, ChevronRight } from "lucide-react";

interface ImageLightboxProps {
  images: string[];
  index: number;
  onClose: () => void;
  onIndexChange: (index: number) => void;
}

export default function ImageLightbox({
  images,
  index,
  onClose,
  onIndexChange,
}: ImageLightboxProps) {
  const hasMany = images.length > 1;
  const prev = () => onIndexChange((index - 1 + images.length) % images.length);
  const next = () => onIndexChange((index + 1) % images.length);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft" && hasMany) prev();
      else if (e.key === "ArrowRight" && hasMany) next();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, images.length, hasMany]);

  const current = images[index];
  if (!current) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <button
        onClick={(e) => {
          e.stopPropagation();
          onClose();
        }}
        aria-label="Đóng"
        className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
      >
        <X size={20} />
      </button>
      {hasMany && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            prev();
          }}
          aria-label="Ảnh trước"
          className="absolute left-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
        >
          <ChevronLeft size={24} />
        </button>
      )}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={current}
        alt={`Ảnh ${index + 1}/${images.length}`}
        onClick={(e) => e.stopPropagation()}
        className="max-h-[85vh] max-w-[90vw] rounded-lg object-contain"
      />
      {hasMany && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            next();
          }}
          aria-label="Ảnh sau"
          className="absolute bottom-4 right-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
        >
          <ChevronRight size={24} />
        </button>
      )}
    </div>
  );
}
