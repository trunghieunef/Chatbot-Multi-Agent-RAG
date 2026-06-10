"""
Generate architecture diagram PNG from the drawio description.
Uses matplotlib for high-quality, publication-ready output.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
import textwrap
import os

# ── Page setup ──────────────────────────────────────────────
FIG_W, FIG_H = 22, 16
fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
ax.set_xlim(0, FIG_W)
ax.set_ylim(0, FIG_H)
ax.axis("off")
ax.set_facecolor("#fafafa")
fig.patch.set_facecolor("#fafafa")

# ── Helper functions ────────────────────────────────────────
def draw_box(ax, x, y, w, h, color, text="", text_color="white", fontsize=9,
             fontweight="normal", edge_color=None, edge_width=1.5, alpha=0.9,
             radius=0.08):
    """Draw a rounded rectangle with centered text."""
    if edge_color is None:
        edge_color = color
    box = FancyBboxPatch((x, y), w, h,
                         boxstyle=f"round,pad=0.05,rounding_size={radius*10}",
                         facecolor=color, edgecolor=edge_color,
                         linewidth=edge_width, alpha=alpha, zorder=3)
    ax.add_patch(box)
    if text:
        lines = text.split("\n")
        y_start = y + h / 2 + (len(lines) - 1) * fontsize * 0.18
        for i, line in enumerate(lines):
            ax.text(x + w / 2, y_start - i * fontsize * 0.36, line,
                    ha="center", va="center", fontsize=fontsize,
                    fontweight=fontweight, color=text_color, zorder=4,
                    fontfamily="sans-serif")

def draw_layer_bg(ax, x, y, w, h, color, alpha=0.12):
    """Draw a dashed rounded rectangle as layer background."""
    box = FancyBboxPatch((x, y), w, h,
                         boxstyle="round,pad=0.1,rounding_size=1.2",
                         facecolor=color, edgecolor=color,
                         linewidth=1.8, linestyle="--", alpha=alpha, zorder=1)
    ax.add_patch(box)

def draw_arrow(ax, x1, y1, x2, y2, color="#555555", lw=1.5, zorder=2,
               style="simple", connectionstyle="arc3,rad=0"):
    """Draw an arrow between two points."""
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=f"-|>" if style == "simple" else "->",
                                color=color, lw=lw,
                                connectionstyle=connectionstyle),
                zorder=zorder)

def layer_label(ax, x, y, text, color, fontsize=11):
    """Add a layer label."""
    ax.text(x, y, text, fontsize=fontsize, fontweight="bold",
            color=color, fontfamily="sans-serif", zorder=5,
            fontstyle="italic")

# ── Title ───────────────────────────────────────────────────
ax.text(FIG_W / 2, FIG_H - 0.5, "KIẾN TRÚC HỆ THỐNG REAL ESTATE CHATBOT PLATFORM",
        ha="center", va="center", fontsize=18, fontweight="bold",
        color="#1a1a2e", fontfamily="sans-serif")

# ── LAYER 1: NGƯỜI DÙNG (y=13.5 to 15.5) ───────────────────
LY1_BOTTOM = 13.3
draw_layer_bg(ax, 0.3, LY1_BOTTOM, FIG_W - 0.6, 2.2, "#4caf50")
layer_label(ax, 0.7, LY1_BOTTOM + 1.9, "NGƯỜI DÙNG", "#4caf50", 12)

# User icons
users = [
    (1.5, "Nguoi dung Web"),
    (5.5, "Nguoi dung Mobile"),
    (9.5, "Quan tri vien"),
]
for ux, uname in users:
    draw_box(ax, ux, LY1_BOTTOM + 0.4, 2.5, 1.1, "#c8e6c9",
             uname, text_color="#1b5e20", fontsize=9,
             fontweight="bold", edge_color="#4caf50", edge_width=1.2,
             alpha=0.85)

# ── Arrows: Users → Frontend ────────────────────────────────
for ux, _ in users:
    draw_arrow(ax, ux + 1.0, LY1_BOTTOM + 0.15,
               FIG_W / 2, LY1_BOTTOM - 0.3,
               color="#1976d2", lw=1.8)

# ── LAYER 2: FRONTEND (y=10.2 to 12.8) ─────────────────────
LY2_BOTTOM = 9.8
draw_layer_bg(ax, 0.3, LY2_BOTTOM, FIG_W - 0.6, 3.2, "#1976d2")
layer_label(ax, 0.7, LY2_BOTTOM + 2.9, "FRONTEND — Next.js 16 + React 19 (Port 3000)", "#1976d2", 12)

# Frontend main box
draw_box(ax, 0.8, LY2_BOTTOM + 0.3, FIG_W - 1.6, 2.3, "#bbdefb",
         "", edge_color="#1976d2", edge_width=1.8, alpha=0.4)

# Frontend pages
fe_pages = [
    (1.2, "Trang chủ"),
    (3.2, "Nhà đất bán"),
    (5.2, "Cho thuê"),
    (7.2, "Thị trường"),
    (9.2, "Admin"),
    (11.2, "Đăng nhập"),
    (13.2, "Chat Widget\n(floating)"),
]
for fx, fname in fe_pages:
    draw_box(ax, fx, LY2_BOTTOM + 1.0, 1.7, 1.0, "#e3f2fd",
             fname, text_color="#0d47a1", fontsize=8,
             edge_color="#1976d2", edge_width=1.2)

ax.text(FIG_W / 2, LY2_BOTTOM + 0.5, "SSR | RSC | App Router | Tailwind CSS v4 | Typed API Client (lib/api.ts)",
        ha="center", va="center", fontsize=8, color="#1565c0",
        fontfamily="monospace")

# ── Arrow: Frontend → Backend ───────────────────────────────
draw_arrow(ax, FIG_W / 2, LY2_BOTTOM - 0.1,
           FIG_W / 2, LY2_BOTTOM - 1.0,
           color="#f57c00", lw=2.2)

# ── LAYER 3: BACKEND & AGENT SERVICE (y=5.0 to 9.5) ────────
LY3_BOTTOM = 4.6
draw_layer_bg(ax, 0.3, LY3_BOTTOM, FIG_W - 0.6, 5.0, "#f57c00")
layer_label(ax, 0.7, LY3_BOTTOM + 4.7, "BACKEND — FastAPI (Port 8000) + Agent Service (Port 8100)", "#f57c00", 12)

# ── Backend API box ─────────────────────────────────────────
BE_X, BE_Y, BE_W, BE_H = 0.7, LY3_BOTTOM + 0.2, 9.8, 4.2
draw_box(ax, BE_X, BE_Y, BE_W, BE_H, "#ffe0b2",
         "", edge_color="#f57c00", edge_width=1.8, alpha=0.35)
ax.text(BE_X + BE_W / 2, BE_Y + BE_H - 0.25, "Backend API (FastAPI + SQLAlchemy 2.0)",
        ha="center", va="center", fontsize=11, fontweight="bold",
        color="#e65100", fontfamily="sans-serif")

# API Routes
routes = [
    (1.0, "/listings\nCRUD+Filter"),
    (2.8, "/market\nStats"),
    (4.6, "/chat\nMulti-Agent"),
    (6.4, "/auth\nJWT"),
    (8.2, "/prefs\nMemory"),
    (1.0, "/admin\nTraces"),
    (2.8, "/metrics\nPrometheus"),
]
for rx, rname in routes:
    draw_box(ax, rx, BE_Y + BE_H - 1.1 - (0 if rx > 3 else 1.9), 1.55, 1.5,
             "#fff3e0", rname, text_color="#bf360c", fontsize=7,
             edge_color="#f57c00", edge_width=1)

# Services
svc_y = BE_Y + 0.45
draw_box(ax, 4.2, svc_y, 2.8, 1.3, "#ffe0b2",
         "Chatbot Pipeline\nrouter->orchestrator\n->agents (x4 parallel)",
         text_color="#bf360c", fontsize=7, fontweight="bold",
         edge_color="#e65100", edge_width=1.2)
draw_box(ax, 7.3, svc_y, 2.8, 1.3, "#ffe0b2",
         "RAG Services\nhybrid_search | embed\nsimple_rag | cache",
         text_color="#bf360c", fontsize=7,
         edge_color="#e65100", edge_width=1.2)

# ── Agent Service box ───────────────────────────────────────
AG_X, AG_Y, AG_W, AG_H = 11.0, LY3_BOTTOM + 0.2, 10.5, 4.2
draw_box(ax, AG_X, AG_Y, AG_W, AG_H, "#e1bee7",
         "", edge_color="#7b1fa2", edge_width=1.8, alpha=0.35)
ax.text(AG_X + AG_W / 2, AG_Y + AG_H - 0.25,
        "Agent Service (FastAPI + LangGraph StateGraph)",
        ha="center", va="center", fontsize=11, fontweight="bold",
        color="#4a148c", fontfamily="sans-serif")

# Agent nodes (8 steps)
nodes = [
    "1.Context\nBuilder", "2.Readiness\nChecker", "3.Router\n(Gemini)",
    "4.Retrieval\nPlanner", "5.Specialist\nAgents (∥)",
    "6.Synthesizer", "7.Safety\nValidator", "8.Memory\nProposals"
]
node_w = 1.2
node_start = AG_X + 0.3
node_y = AG_Y + AG_H - 1.25
for i, n in enumerate(nodes):
    nx = node_start + i * (node_w + 0.05)
    is_highlight = (i == 4)
    draw_box(ax, nx, node_y, node_w, 0.95,
             "#ce93d8" if is_highlight else "#f3e5f5",
             n, text_color="#4a148c" if not is_highlight else "white",
             fontsize=6, fontweight="bold" if is_highlight else "normal",
             edge_color="#7b1fa2", edge_width=1)
    if i > 0:
        draw_arrow(ax, nx - 0.1, node_y + 0.47,
                   nx + 0.05, node_y + 0.47,
                   color="#7b1fa2", lw=1)

# Specialist agents
specs = ["Property\nSearch", "Market\nAnalysis",
         "Legal\nAdvisor", "Investment\nAdvisor"]
spec_y = AG_Y + 1.2
for i, s in enumerate(specs):
    draw_box(ax, AG_X + 0.3 + i * 2.55, spec_y, 2.3, 0.95,
             "#e1bee7", s, text_color="#4a148c", fontsize=7,
             edge_color="#7b1fa2", edge_width=1)

# Tools
tools = ["retrieval.py", "market.py", "readiness.py", "legal_synth"]
tool_y = AG_Y + 0.25
for i, t in enumerate(tools):
    draw_box(ax, AG_X + 0.3 + i * 2.55, tool_y, 2.3, 0.65,
             "#f5f5f5", t, text_color="#424242", fontsize=6.5,
             edge_color="#9e9e9e", edge_width=0.8)

# LLM & Judge
draw_box(ax, AG_X + AG_W - 3.8, spec_y, 3.3, 0.8,
         "#f3e5f5", "Gemini 2.0 Flash (LLM)", text_color="#4a148c",
         fontsize=8, fontweight="bold", edge_color="#7b1fa2", edge_width=1)
draw_box(ax, AG_X + AG_W - 3.8, tool_y, 3.3, 0.65,
         "#f3e5f5", "LLM Judge (5 metrics)", text_color="#4a148c",
         fontsize=8, edge_color="#7b1fa2", edge_width=1)

# Arrow: Backend → Agent
draw_arrow(ax, BE_X + BE_W + 0.05, BE_Y + BE_H / 2,
           AG_X - 0.05, AG_Y + AG_H / 2,
           color="#7b1fa2", lw=1.8, style="simple")

# ── Arrow: Backend → Data ───────────────────────────────────
draw_arrow(ax, FIG_W / 2 - 2, LY3_BOTTOM - 0.1,
           FIG_W / 2 - 2, LY3_BOTTOM - 0.9,
           color="#d32f2f", lw=2.2)

# ── LAYER 4: DATA (y=2.0 to 4.3) ───────────────────────────
LY4_BOTTOM = 1.6
draw_layer_bg(ax, 0.3, LY4_BOTTOM, FIG_W - 0.6, 2.8, "#d32f2f")
layer_label(ax, 0.7, LY4_BOTTOM + 2.5, "DỮ LIỆU — PostgreSQL 16 + pgvector & Redis 7", "#d32f2f", 12)

# Database boxes
db_items = [
    (1.0, 4.5, "PostgreSQL 16 + pgvector\n\n• Bảng listings (30+ trường)\n• Bảng chunks (VECTOR 1024)\n• HNSW index (m=16, ef=64)\n• Polymorphic chunks\n• 14+ bảng quan hệ"),
    (6.0, 4.5, "Redis 7 Alpine\n\n• Embedding Cache\n  (key: provider:model:dim:hash)\n• Search Result Cache\n• Session Store\n• TTL-based expiry"),
    (11.0, 4.5, "Observability\n\n• agent_traces\n• agent_trace_steps\n• agent_llm_calls\n• agent_retrieval_events\n• pipeline_runs\n• source_readiness"),
]
for dx, dw, dtext in db_items:
    draw_box(ax, dx, LY4_BOTTOM + 0.2, dw, 2.3, "#ffcdd2",
             dtext, text_color="#b71c1c", fontsize=7.5,
             edge_color="#d32f2f", edge_width=1.5, alpha=0.7)

# ── Arrow: Data → Pipeline ──────────────────────────────────
draw_arrow(ax, FIG_W / 2, LY4_BOTTOM - 0.1,
           FIG_W / 2, LY4_BOTTOM - 0.9,
           color="#616161", lw=2.2)

# ── LAYER 5: DATA PIPELINE (y=0 to 1.4) ────────────────────
LY5_BOTTOM = -0.2
draw_layer_bg(ax, 0.3, LY5_BOTTOM, FIG_W - 0.6, 1.65, "#616161")
layer_label(ax, 0.7, LY5_BOTTOM + 1.35, "DATA PIPELINE & TỰ ĐỘNG HÓA", "#616161", 12)

pipeline_steps = [
    "Crawlers\n(Playwright\n+ Stealth)",
    "Clean\n(Parse gia,\ndien tich)",
    "Enrich\n(Geocode+\nIntent Tag)",
    "Chunk\n(Overview,\nDesc, Loc)",
    "Embed\n(BGE-M3\n1024d)",
    "Load DB\n(Upsert\nPostgreSQL)",
    "Airflow\n(4 DAGs:\nDaily/Weekly)",
    "Monitor\n(Prometheus\n+ Slack Alert)",
]
step_w = 2.4
for i, s in enumerate(pipeline_steps):
    draw_box(ax, 0.5 + i * (step_w + 0.15), LY5_BOTTOM + 0.15,
             step_w, 1.1, "#e0e0e0",
             s, text_color="#212121", fontsize=6.5,
             edge_color="#616161", edge_width=1.2, alpha=0.8)
    if i > 0:
        draw_arrow(ax, 0.5 + i * (step_w + 0.15) - 0.08,
                   LY5_BOTTOM + 0.7,
                   0.5 + i * (step_w + 0.15) + 0.05,
                   LY5_BOTTOM + 0.7,
                   color="#424242", lw=1.5)

# ── Vertical connection labels ──────────────────────────────
ax.text(FIG_W - 1.0, LY1_BOTTOM + 0.4, "HTTP/HTTPS", fontsize=7,
        color="#1976d2", rotation=90, va="center", fontfamily="monospace")
ax.text(FIG_W - 1.0, LY2_BOTTOM + 1.0, "REST API", fontsize=7,
        color="#f57c00", rotation=90, va="center", fontfamily="monospace")
ax.text(FIG_W - 1.0, LY3_BOTTOM + 2.0, "Internal Key Auth", fontsize=7,
        color="#7b1fa2", rotation=90, va="center", fontfamily="monospace")
ax.text(FIG_W - 1.0, LY4_BOTTOM + 1.0, "asyncpg / Redis", fontsize=7,
        color="#d32f2f", rotation=90, va="center", fontfamily="monospace")

# ── Legend ──────────────────────────────────────────────────
legend_items = [
    ("#4caf50", "User Layer"),
    ("#1976d2", "Frontend"),
    ("#f57c00", "Backend API"),
    ("#7b1fa2", "Agent Service"),
    ("#d32f2f", "Data Layer"),
    ("#616161", "Pipeline"),
]
lx, ly = 0.5, -0.15
for i, (lc, ll) in enumerate(legend_items):
    ax.add_patch(plt.Rectangle((lx + i * 1.8, ly), 0.3, 0.15,
                                facecolor=lc, edgecolor="gray",
                                linewidth=0.5, alpha=0.8))
    ax.text(lx + i * 1.8 + 0.4, ly + 0.07, ll, fontsize=6.5,
            color="#333333", va="center")

# ── Save ────────────────────────────────────────────────────
os.makedirs("report/figures", exist_ok=True)
outpath = "report/figures/architecture.png"
fig.savefig(outpath, dpi=200, bbox_inches="tight",
            facecolor=fig.get_facecolor(), edgecolor="none")
plt.close(fig)
print(f"[OK] Saved architecture diagram to {outpath}")
print(f"   Resolution: {int(FIG_W*200)}x{int(FIG_H*200)} px @ 200 DPI")
