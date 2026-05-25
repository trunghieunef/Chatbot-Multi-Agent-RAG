from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings


SYSTEM_PROMPT = (
    "Bạn là chuyên viên tư vấn pháp lý bất động sản. "
    "Trả lời chỉ dựa trên các trích dẫn cung cấp. "
    "Nếu không có trích dẫn liên quan, hãy nói rõ là chưa có cơ sở pháp lý. "
    "Mỗi luận điểm phải kèm trích dẫn theo dạng (slug-văn-bản, Điều X)."
)


def format_citations(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "Không có trích dẫn pháp lý phù hợp."

    lines: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        citation = chunk.get("citation") or {}
        slug = (
            citation.get("doc_slug")
            or (chunk.get("metadata_json") or {}).get("slug")
            or "không rõ"
        )
        chuong = citation.get("chuong") or ""
        dieu = citation.get("dieu_number")
        dieu_title = citation.get("dieu_title") or ""
        khoan = citation.get("khoan_number")

        parts: list[str] = [slug]
        if chuong:
            parts.append(chuong)
        if dieu is not None:
            dieu_part = f"Điều {dieu}"
            if dieu_title:
                dieu_part += f" - {dieu_title}"
            parts.append(dieu_part)
        if khoan is not None:
            parts.append(f"Khoản {khoan}")
        header = f"[{index}] (" + ", ".join(parts) + ")"

        snippet = (chunk.get("text") or "").strip().replace("\n", " ")
        if len(snippet) > 600:
            snippet = snippet[:600] + "..."
        lines.append(f"{header}\n{snippet}")
    return "\n\n".join(lines)


def build_legal_prompt(query: str, chunks: list[dict[str, Any]]) -> str:
    citations_block = format_citations(chunks)
    if not chunks:
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"Câu hỏi: {query}\n\n"
            "Hệ thống không tìm thấy trích dẫn pháp lý phù hợp. "
            "Hãy trả lời rằng cần thêm thông tin hoặc đề nghị người dùng tham vấn luật sư."
        )
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"Câu hỏi: {query}\n\n"
        f"Trích dẫn pháp lý:\n{citations_block}\n\n"
        "Hãy trả lời ngắn gọn, có cấu trúc, và dẫn chiếu chính xác."
    )


async def synthesize_legal_answer(query: str, chunks: list[dict[str, Any]]) -> str:
    settings = get_settings()
    prompt = build_legal_prompt(query, chunks)

    if not settings.GEMINI_API_KEY:
        return prompt  # fallback returns the structured prompt itself

    from google import genai

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=settings.GEMINI_MODEL,
        contents=prompt,
    )
    return response.text or "Không thể tạo phản hồi pháp lý lúc này."
