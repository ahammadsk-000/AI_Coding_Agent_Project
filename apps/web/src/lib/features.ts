/**
 * Build-time feature flags (Vite bakes these at build).
 *
 * SANDBOX_ENABLED — the sandbox needs a host Docker socket, which managed PaaS
 * (e.g. the Render/Vercel free-tier deploy) does not provide, so it's hidden
 * there. It defaults to OFF; set `VITE_SANDBOX_ENABLED=true` (the local
 * docker-compose stack does) to show the Sandbox nav item + route.
 */
export const SANDBOX_ENABLED = import.meta.env.VITE_SANDBOX_ENABLED === "true";
