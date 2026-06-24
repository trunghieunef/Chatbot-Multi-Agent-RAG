"use client";

import { useState } from "react";
import ImageLightbox from "./ImageLightbox";

interface ListingImageGalleryProps {
  images: string[];
}

export default function ListingImageGallery({ images }: ListingImageGalleryProps) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [broken, setBroken] = useState<Set<number>>(new Set());

  const shown = images.slice(0, 3);
  if (shown.length === 0 || shown.every((_, i) => broken.has(i))) return null;

  return (
    <>
      <div className="mt-1.5 flex gap-1.5">
        {shown.map((url, i) =>
          broken.has(i) ? null : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={i}
              src={url}
              alt={`Ảnh ${i + 1}`}
              loading="lazy"
              onClick={() => setOpenIndex(i)}
              onError={() =>
                setBroken((b) => {
                  const nextSet = new Set(b);
                  nextSet.add(i);
                  return nextSet;
                })
              }
              className="h-16 w-16 cursor-pointer rounded-md object-cover transition-opacity hover:opacity-90"
            />
          )
        )}
      </div>
      {openIndex !== null && (
        <ImageLightbox
          images={shown}
          index={openIndex}
          onClose={() => setOpenIndex(null)}
          onIndexChange={setOpenIndex}
        />
      )}
    </>
  );
}
