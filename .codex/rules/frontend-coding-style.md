---
paths:
  - frontend/**/*
---
# Frontend Coding Style

- Framework: Next.js 14+ App Router (`app/` directory).
- Styling: Tailwind CSS v4 via PostCSS plugin (`@tailwindcss/postcss`). NOT v3 config-based. No `tailwind.config.ts`.
- Language: TypeScript strict mode.
- Components: functional components + React hooks only.
- Naming: `PascalCase` for component files (`.tsx`), `camelCase` for functions/variables, `.ts` for utilities.
- Icons: use `lucide-react` exclusively.
- Charts: use `recharts`.
- API calls: centralized in `frontend/lib/api.ts`.
- Types: defined in `frontend/lib/types.ts`.
- Read `frontend/CLAUDE.md` before changing Next.js configuration or behavior.
