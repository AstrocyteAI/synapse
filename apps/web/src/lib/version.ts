// Friendly re-export of the build-time global `__APP_VERSION__` so call
// sites don't have to type the underscore-noise. The actual value comes
// from `git describe --tags --abbrev=0` at build time — see
// `vite.config.ts` for the injection. Falls back to "0.0.0-dev" when
// git is unavailable.
export const appVersion: string = __APP_VERSION__;
