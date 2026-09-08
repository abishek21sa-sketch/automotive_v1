import adapter from '@sveltejs/adapter-node';
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

			// adapter-node: self-hostable standalone Node.js server, not tied to
			// a specific platform like Vercel/Netlify. `npm run build` produces
			// build/, run in production with `node build/index.js`.
			adapter: adapter()
		})
	]
});
