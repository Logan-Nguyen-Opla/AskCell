/**
 * Backend base URL for fetch/XHR calls.
 *
 * - Unset / empty: same origin (Vite dev proxy or reverse proxy in production).
 * - Set VITE_API_URL: direct calls (e.g. Vercel frontend -> Render backend).
 */
export const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
