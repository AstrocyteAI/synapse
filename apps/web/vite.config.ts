import { execSync } from 'node:child_process';
import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// Single source of truth for the app's displayed version: the latest
// annotated git tag (stripped of leading "v"). Computed once at config
// load, baked into the bundle via Vite's `define`. Available as the
// global `__APP_VERSION__` in any .svelte / .ts file.
//
// Falls back to "0.0.0-dev" when git is unavailable (e.g. building from
// a tarball with no .git/ directory). The package.json `version` field
// is irrelevant — this app isn't published, only built.
//
// To display: `import { app_version } from '$lib/version'` (or just
// reference `__APP_VERSION__` directly with a type declaration).
const appVersion = (() => {
	try {
		return execSync('git describe --tags --abbrev=0', {
			encoding: 'utf8',
			stdio: ['ignore', 'pipe', 'ignore']
		})
			.trim()
			.replace(/^v/, '');
	} catch {
		return '0.0.0-dev';
	}
})();

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	define: {
		__APP_VERSION__: JSON.stringify(appVersion)
	}
});
