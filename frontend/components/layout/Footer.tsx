import Link from "next/link";
import { Mail, MapPin, Phone } from "lucide-react";

export default function Footer() {
  return (
    <footer className="mt-auto border-t border-border bg-card">
      <div className="mx-auto max-w-7xl px-4 py-12">
        <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <Link href="/" className="flex items-center gap-2 mb-4">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-sm">
                B
              </span>
              <strong className="text-sm">batdongsan</strong>
            </Link>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Nen tang tim kiem bat dong san tich hop chatbot AI tu van thong
              minh 24/7.
            </p>
          </div>

          <div>
            <h3 className="mb-4 text-sm font-semibold text-foreground">
              Danh muc
            </h3>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li>
                <Link
                  href="/nha-dat-ban"
                  className="hover:text-primary transition-colors"
                >
                  Nha dat ban
                </Link>
              </li>
              <li>
                <Link
                  href="/nha-dat-cho-thue"
                  className="hover:text-primary transition-colors"
                >
                  Nha dat cho thue
                </Link>
              </li>
              <li>
                <Link
                  href="/du-an"
                  className="hover:text-primary transition-colors"
                >
                  Du an
                </Link>
              </li>
              <li>
                <Link
                  href="/tin-tuc"
                  className="hover:text-primary transition-colors"
                >
                  Tin tuc
                </Link>
              </li>
              <li>
                <Link
                  href="/thi-truong"
                  className="hover:text-primary transition-colors"
                >
                  Du lieu thi truong
                </Link>
              </li>
            </ul>
          </div>

          <div>
            <h3 className="mb-4 text-sm font-semibold text-foreground">Ho tro</h3>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li>Cau hoi thuong gap</li>
              <li>Huong dan su dung</li>
              <li>Dieu khoan su dung</li>
              <li>Chinh sach bao mat</li>
            </ul>
          </div>

          <div>
            <h3 className="mb-4 text-sm font-semibold text-foreground">
              Lien he
            </h3>
            <ul className="space-y-3 text-sm text-muted-foreground">
              <li className="flex items-center gap-2">
                <Mail size={14} className="text-primary" />
                hieu21268@gmail.com
              </li>
              <li className="flex items-center gap-2">
                <Phone size={14} className="text-primary" />
                1900 1881
              </li>
              <li className="flex items-start gap-2">
                <MapPin size={14} className="mt-0.5 text-primary" />
                Khoa Toan-Tin, Dai hoc Bach Khoa Ha Noi
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-10 border-t border-border pt-6 text-center text-xs text-muted-foreground">
          (c) {new Date().getFullYear()} BatDongSan Chatbot. Phat trien boi
          TrungHieu145.
        </div>
      </div>
    </footer>
  );
}
