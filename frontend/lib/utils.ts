import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatPrice(price: number | null | undefined): string {
  if (price == null) return "Liên hệ";
  if (price >= 1) return `${price.toFixed(1)} tỷ`;
  return `${(price * 1000).toFixed(0)} triệu`;
}

/** Split description by | (pipe) into separate lines for display. */
export function formatDescription(text: string | null | undefined): string {
  if (!text) return "";
  return text
    .split("|")
    .map((s) => s.trim())
    .filter(Boolean)
    .join("\n");
}

export function truncate(str: string | null | undefined, max = 80): string {
  if (!str) return "";
  return str.length > max ? str.slice(0, max) + "…" : str;
}
