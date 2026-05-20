# @aca/web

React + Vite + TypeScript frontend for the AI Coding Agent Platform.

## Stack

- React 18, React Router 6
- TanStack Query (server state) + Zustand (client/auth state)
- Tailwind CSS + shadcn-style primitives copied into `components/ui/`
- Vite for dev/build, Vitest for tests

## Scripts

```bash
pnpm install
pnpm dev         # http://localhost:3000
pnpm build       # type-check + production build
pnpm test        # vitest
pnpm lint
```

## Notes

- API base URL is set via `VITE_API_BASE_URL` (defaults to http://localhost:8000).
- Auth tokens are persisted to `localStorage` under the `aca.auth` key.
- Monaco editor + agent activity panels arrive in Phase 2 / Phase 4.
