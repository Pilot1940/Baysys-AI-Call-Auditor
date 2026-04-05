# BaySys Call Audit UI

React 18 + Vite + TypeScript + Tailwind frontend for BaySys AI Call Auditor.

In production this builds into the CRM alongside Voice Trainer. In development it runs standalone with a proxy to the Django backend.

## Prerequisites

- Node 18+
- npm 9+
- Django backend running on `http://localhost:8000`

## Setup

```bash
cd baysys_call_audit_ui/
npm install
```

## Development

```bash
npm run dev
```

Opens at `http://localhost:5173`. All `/audit` API requests are proxied to `http://localhost:8000` via `vite.config.ts`. No CORS issues.

```bash
# Django backend (separate terminal)
cd ..
source .venv/bin/activate
python manage.py runserver --settings=settings
```

## Build

```bash
npm run build        # outputs to dist/
npm run preview      # preview the production build locally
```

## Type checking + lint

```bash
npm run type-check   # tsc --noEmit
npx eslint src/      # if eslint is configured
```

## Auth

In development the app uses `MockAuthContext` (role_id=2, Manager/TL scope). To test different roles, edit `src/mock/MockAuthContext.tsx`:

```tsx
const mockUser = { user_id: "1", role_id: 1 }; // 1=Admin, 2=Manager/TL, 3=Agent
```

In production the CRM injects its own auth context — `MockAuthContext` is not used.

## Pages

| Route | Component | Notes |
|-------|-----------|-------|
| `/audit` | `DashboardPage` | Score distributions, compliance heatmap, agent table |
| `/audit/call/:id` | `CallDetailPage` | Transcript, scores, compliance flags |

## Key files

| File | Purpose |
|------|---------|
| `src/types/audit.ts` | TypeScript interfaces for all API response types |
| `src/utils/Api.tsx` | Typed API client (recordings, dashboard, compliance flags) |
| `src/utils/Request.tsx` | HTTP helper with auth headers |
| `src/mock/MockAuthContext.tsx` | Dev-only auth provider |
| `vite.config.ts` | Dev server config + `/audit` proxy |
