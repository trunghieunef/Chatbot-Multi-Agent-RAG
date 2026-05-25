import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatPrice(price: number | null | undefined): string {
  if (price == null) return "Liên hệ";
  if (price >= 1) return `${price.toFixed(1)} tỷ`;
  return `${(price * 1000).toFixed(0)} triệu`;
}

export function truncate(str: string | null | undefined, max = 80): string {
  if (!str) return "";
  return str.length > max ? str.slice(0, max) + "…" : str;
}
