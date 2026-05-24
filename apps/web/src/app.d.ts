// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}

	// Build-time injection from vite.config.ts (`define` block).
	// Source: `git describe --tags --abbrev=0` of the synapse repo
	// at build time, with leading "v" stripped. Falls back to
	// "0.0.0-dev" when git is unavailable. Use it in any .svelte or
	// .ts file to render the current app version.
	const __APP_VERSION__: string;
}

export {};
