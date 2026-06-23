import type { ChatMessageResponse, ChatSource } from "@/lib/types";

const source = (
  title: string,
  url: string,
  score: number,
  extra: Partial<ChatSource> = {}
): ChatSource => ({
  type: extra.type || "listing",
  domain: extra.domain || "property",
  title,
  url,
  score,
  ...extra,
  metadata: { demo: true, ...(extra.metadata || {}) },
});

const propertySources: ChatSource[] = [
  source("Căn hộ chung cư ABC", "/nha-dat-ban/demo-abc", 0.95, {
    id: "demo-abc",
    location: "Phường Tân Phong, Quận 7",
    metadata: { price_text: "4,2 tỷ", area_text: "72m2" },
  }),
  source("Căn hộ Sunshine City", "/nha-dat-ban/demo-sunshine", 0.89, {
    id: "demo-sunshine",
    location: "Phường Phú Thuận, Quận 7",
    metadata: { price_text: "4,8 tỷ", area_text: "78m2" },
  }),
  source("Căn hộ Park View", "/nha-dat-ban/demo-park-view", 0.82, {
    id: "demo-park-view",
    location: "Phường Tân Quy, Quận 7",
    metadata: { price_text: "3,9 tỷ", area_text: "68m2" },
  }),
];

const mixedSources: ChatSource[] = [
  source("Hướng dẫn sang tên sổ đỏ", "/tin-tuc/demo-sang-ten-so-do", 0.94, {
    id: "demo-legal-1",
    type: "article",
    domain: "legal",
    citation: "KB Pháp lý 1",
  }),
  source("Thuế phí khi chuyển nhượng nhà đất", "/tin-tuc/demo-thue-phi", 0.9, {
    id: "demo-legal-2",
    type: "article",
    domain: "legal",
    citation: "KB Pháp lý 2",
  }),
  source("Thống kê giá đất Quận 9", "/thi-truong?district=Quan%209", 0.87, {
    id: "demo-market-q9",
    type: "market_metric",
    domain: "market",
    location: { district: "Quận 9", city: "Hồ Chí Minh" },
    metadata: { range: "35-90 triệu/m2" },
  }),
];

function propertyDemoResponse(sessionId: string): ChatMessageResponse {
  return {
    session_id: sessionId,
    role: "assistant",
    agent_used: "property_search",
    agents_used: ["property_search"],
    request_id: `demo-${Date.now()}`,
    created_at: new Date().toISOString(),
    trace_summary: {
      intent: "property_search",
      agents: ["property_search"],
      source_count: propertySources.length,
      latency_ms: 420,
      warnings: [],
    },
    sources: propertySources,
    suggested_actions: [
      "So sanh gia/m2 cac can ho nay",
      "Thu tuc phap ly khi mua chung cu can nhung gi?",
      "Khu vuc Quan 7 co tiem nang tang gia khong?",
    ],
    content: [
      "Intent: property_search",
      "Agent sử dụng: property_search",
      'Bộ lọc trích xuất: {listing_type: "sale", property_type: "apartment", district: "Quận 7", max_price: 5, bedrooms: 2}',
      "",
      "Phản hồi: Dựa trên yêu cầu của bạn, tôi tìm thấy một số căn hộ phù hợp tại Quận 7:",
      "",
      "1. Căn hộ chung cư ABC - 4,2 tỷ, 72m2, 2PN, 2WC, Phường Tân Phong.",
      "   View sông, nội thất đầy đủ, pháp lý sổ hồng.",
      "",
      "2. Căn hộ Sunshine City - 4,8 tỷ, 78m2, 2PN, 1WC, Phường Phú Thuận.",
      "   Gần trường học, an ninh tốt, có hồ bơi.",
      "",
      "3. Căn hộ Park View - 3,9 tỷ, 68m2, 2PN, 1WC, Phường Tân Quy.",
      "   Giá tốt nhất khu vực, gần siêu thị.",
      "",
      "Nguồn tham khảo: [Link BĐS 1] (độ liên quan: 0.95), [Link BĐS 2] (0.89), [Link BĐS 3] (0.82)",
      "",
      "Gợi ý tiếp theo:",
      '- "So sánh giá/m2 các căn hộ này"',
      '- "Thủ tục pháp lý khi mua chung cư cần những gì?"',
      '- "Khu vực Quận 7 có tiềm năng tăng giá không?"',
    ].join("\n"),
  };
}

function mixedDemoResponse(sessionId: string): ChatMessageResponse {
  return {
    session_id: sessionId,
    role: "assistant",
    agent_used: "legal_advisor, market_analysis",
    agents_used: ["legal_advisor", "market_analysis"],
    request_id: `demo-${Date.now()}`,
    created_at: new Date().toISOString(),
    trace_summary: {
      intent: "mixed",
      agents: ["legal_advisor", "market_analysis"],
      source_count: mixedSources.length,
      latency_ms: 610,
      warnings: [],
    },
    sources: mixedSources,
    suggested_actions: [
      "Các loại thuế phí khi mua đất là gì?",
      "So sánh giá đất Quận 9 với Quận 2 và Thủ Đức",
      "Có nên đầu tư đất nền Quận 9 thời điểm này?",
    ],
    content: [
      "Intent: mixed (legal_advice + market_analysis)",
      "Agent sử dụng: legal_advisor, market_analysis",
      "",
      "Phản hồi: Tôi sẽ giải đáp từng phần câu hỏi của bạn:",
      "",
      "1. Thủ tục sang tên sổ đỏ:",
      "Theo quy định hiện hành, thủ tục sang tên sổ đỏ (chuyển nhượng quyền sử dụng đất) gồm các bước chính:",
      "- Công chứng hợp đồng chuyển nhượng tại văn phòng công chứng (1-2 ngày).",
      "- Kê khai thuế thu nhập cá nhân và lệ phí trước bạ tại Chi cục Thuế (3-5 ngày).",
      "- Nộp hồ sơ sang tên tại Văn phòng Đăng ký Đất đai (10-15 ngày làm việc).",
      "",
      "Tổng thời gian ước tính: 3-5 tuần tùy địa phương.",
      "",
      "Lưu ý quan trọng: Cần kiểm tra đất không có tranh chấp, không bị quy hoạch, và đã hoàn thành nghĩa vụ tài chính.",
      "",
      "2. Giá đất tại Quận 9:",
      "Hiện tại (dữ liệu cập nhật từ hệ thống):",
      "- Giá đất nền trung bình: 35-55 triệu/m2 tùy vị trí.",
      "- Giá đất mặt tiền đường lớn: 60-90 triệu/m2.",
      "- Xu hướng: tăng nhẹ 5-8% so với cùng kỳ năm trước, được thúc đẩy bởi hạ tầng giao thông (Metro, Vành đai 3).",
      "",
      "Nguồn tham khảo: [Link KB Pháp lý 1], [Link KB Pháp lý 2], [Link Thống kê Quận 9]",
      "",
      "Gợi ý tiếp theo:",
      '- "Các loại thuế phí khi mua đất là gì?"',
      '- "So sánh giá đất Quận 9 với Quận 2 và Thủ Đức"',
      '- "Có nên đầu tư đất nền Quận 9 thời điểm này?"',
    ].join("\n"),
  };
}

export function buildDemoChatResponse(
  message: string,
  sessionId: string
): ChatMessageResponse {
  const normalized = message
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  if (
    normalized.includes("sang ten") ||
    normalized.includes("so do") ||
    normalized.includes("quan 9") ||
    normalized.includes("gia dat")
  ) {
    return mixedDemoResponse(sessionId);
  }
  return propertyDemoResponse(sessionId);
}

export function isDemoChatEnabled(): boolean {
  if (process.env.NEXT_PUBLIC_CHAT_DEMO_MODE === "true") return true;
  if (typeof window === "undefined") return false;
  const params = new URLSearchParams(window.location.search);
  return (
    params.get("demo") === "1" ||
    window.localStorage.getItem("chat_demo_mode") === "1"
  );
}
