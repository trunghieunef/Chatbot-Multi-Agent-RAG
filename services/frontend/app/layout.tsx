import type { Metadata } from "next";
import "./globals.css";
import Header from "@/components/layout/Header";
import Footer from "@/components/layout/Footer";
import ChatWidget from "@/components/chatbot/ChatWidget";

export const metadata: Metadata = {
  title: {
    default: "BatDongSan — Nền tảng BĐS tích hợp AI",
    template: "%s | BatDongSan",
  },
  description:
    "Tìm kiếm bất động sản nhanh chóng, tư vấn bởi chatbot AI thông minh. Nhà đất bán, cho thuê, dự án mới nhất.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi" className="h-full antialiased">
      <body className="min-h-full flex flex-col font-sans">
        <Header />
        <main className="flex-1">{children}</main>
        <Footer />
        <ChatWidget />
      </body>
    </html>
  );
}
