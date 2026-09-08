// Set VITE_API_BASE at build time for any deployment other than local dev
// (e.g. `VITE_API_BASE=https://api.example.com npm run build`). Falls back
// to the local backend so `npm run dev` keeps working with zero config.
export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8010';
