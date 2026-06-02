import Link from "next/link";
import { Mail, Phone, MapPin } from "lucide-react";

export default function Footer() {
  return (
    <footer className="mt-auto border-t border-border bg-card">
      <div className="mx-auto max-w-7xl px-4 py-12">
        <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          {/* Brand */}
          <div>
            <Link href="/" className="flex items-center gap-2 mb-4">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-sm">
                B
              </span>
              <strong className="text-sm">batdongsan</strong>
            </Link>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Nền tảng tìm kiếm bất động sản hàng đầu, tích hợp chatbot AI tư
              vấn thông minh 24/7.
            </p>
          </div>

          {/* Quick Links */}
          <div>
            <h3 className="mb-4 text-sm font-semibold text-foreground">
              Danh mục
            </h3>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li>
                <Link
                  href="/nha-dat-ban"
                  className="hover:text-primary transition-colors"
                >
                  Nhà đất bán
                </Link>
              </li>
              <li>
                <Link
                  href="/nha-dat-cho-thue"
                  className="hover:text-primary transition-colors"
                >
                  Nhà đất cho thuê
                </Link>
              </li>
              <li>
                <Link
                  href="/thi-truong"
                  className="hover:text-primary transition-colors"
                >
                  Dữ liệu thị trường
                </Link>
              </li>
            </ul>
          </div>

          {/* Support */}
          <div>
            <h3 className="mb-4 text-sm font-semibold text-foreground">
              Hỗ trợ
            </h3>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li>Câu hỏi thường gặp</li>
              <li>Hướng dẫn sử dụng</li>
              <li>Điều khoản sử dụng</li>
              <li>Chính sách bảo mật</li>
            </ul>
          </div>

          {/* Contact */}
          <div>
            <h3 className="mb-4 text-sm font-semibold text-foreground">
              Liên hệ
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
                Khoa Toán-Tin , Đại học Bách Khoa Hà Nội
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-10 border-t border-border pt-6 text-center text-xs text-muted-foreground">
          © {new Date().getFullYear()} BatDongSan Chatbot. Phát triển bởi TrungHieu145.
        </div>
      </div>
    </footer>
  );
}
