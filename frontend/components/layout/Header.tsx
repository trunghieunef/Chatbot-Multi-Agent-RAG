"use client";

import Link from "next/link";
import { useState } from "react";
import { Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "/nha-dat-ban", label: "Nha dat ban" },
  { href: "/nha-dat-cho-thue", label: "Nha dat cho thue" },
  { href: "/du-an", label: "Du an" },
  { href: "/tin-tuc", label: "Tin tuc" },
  { href: "/thi-truong", label: "Thi truong" },
];

export default function Header() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 glass shadow-sm">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2 group">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground font-extrabold text-lg transition-transform group-hover:scale-110">
            B
          </span>
          <div className="hidden sm:block leading-tight">
            <strong className="text-sm text-foreground">batdongsan</strong>
            <span className="block text-[10px] text-muted-foreground">
              Kenh thong tin nha dat
            </span>
          </div>
        </Link>

        <nav className="hidden md:flex items-center gap-1">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="rounded-lg px-3 py-2 text-sm font-medium text-foreground/80 transition-colors hover:bg-muted hover:text-foreground"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="hidden md:flex items-center gap-2">
          <Link
            href="/dang-nhap"
            className="rounded-lg px-4 py-2 text-sm font-medium text-foreground/80 transition-colors hover:bg-muted"
          >
            Dang nhap
          </Link>
          <Link
            href="/dang-ky"
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary-hover"
          >
            Dang ky
          </Link>
        </div>

        <button
          onClick={() => setOpen(!open)}
          className="md:hidden rounded-lg p-2 text-foreground/80 hover:bg-muted transition-colors"
          aria-label="Toggle menu"
        >
          {open ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>

      <div
        className={cn(
          "md:hidden overflow-hidden transition-all duration-300 ease-in-out",
          open ? "max-h-80 border-t border-border" : "max-h-0"
        )}
      >
        <nav className="flex flex-col px-4 py-3 gap-1">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setOpen(false)}
              className="rounded-lg px-3 py-2.5 text-sm font-medium text-foreground/80 hover:bg-muted hover:text-foreground transition-colors"
            >
              {link.label}
            </Link>
          ))}
          <hr className="my-2 border-border" />
          <Link
            href="/dang-nhap"
            onClick={() => setOpen(false)}
            className="rounded-lg px-3 py-2.5 text-sm font-medium text-foreground/80 hover:bg-muted transition-colors"
          >
            Dang nhap
          </Link>
          <Link
            href="/dang-ky"
            onClick={() => setOpen(false)}
            className="rounded-lg bg-primary px-3 py-2.5 text-center text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary-hover"
          >
            Dang ky
          </Link>
        </nav>
      </div>
    </header>
  );
}
