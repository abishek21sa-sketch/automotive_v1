import adapter from '@sveltejs/adapter-vercel';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	worker: {
		// maplibre-gl ships an ESM worker bundle; Vite's IIFE default breaks it
		// ("does not provide an export named 'default'") both in dev and build.
		format: 'es'
	},
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// The backend (FastAPI + a 644MB DuckDB warehouse) can't run on
			// Vercel's serverless functions, so only the frontend deploys there.
			adapter: adapter()
		})
	]
});
