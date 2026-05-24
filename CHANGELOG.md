# Changelog

All notable changes to Synapse (web + Flutter + OSS backend) are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Web Docker build broken by stale `pnpm-workspace.yaml`.** The v0.2.1
  fix landed `pnpm.onlyBuiltDependencies` in `apps/web/package.json`,
  but pnpm 10.4+ reads workspace-wide build-script allowlists from
  `pnpm-workspace.yaml` first and that file had `protobufjs` in
  `ignoredBuiltDependencies` — explicitly suppressing it. Moved
  `protobufjs` into `onlyBuiltDependencies` and dropped the now-redundant
  `pnpm` block from `package.json`.

## [0.2.1] — 2026-05-24

Patch release — CI unblock + build-tooling polish that landed shortly
after v0.2.0 but wasn't captured in its notes.

### Fixed

- **Web Docker build broken by pnpm v10+ install-script protection.**
  pnpm 10 refuses to run install scripts from transitive dependencies
  unless allowlisted; `protobufjs` (pulled in by `centrifuge`) needs
  its install script to compile descriptors. Added
  `"pnpm": { "onlyBuiltDependencies": ["protobufjs"] }` to
  `apps/web/package.json` so CI's `pnpm install --frozen-lockfile`
  succeeds.

### Changed

- **Web: build version derived from git tag.** `vite.config.ts` injects a
  `__APP_VERSION__` global from `git describe --tags --abbrev=0` at
  build time. A friendly re-export lives at `$lib/version` —
  `import { appVersion } from '$lib/version'` to display. Falls back
  to `0.0.0-dev` when git is unavailable.
- **Flutter: documented `--build-name`/`--build-number` build flags.**
  The Flutter app's `pubspec.yaml` version remains the App Store /
  Play Store binary version (separate cadence); CI builds should pass
  the synapse git tag in via `--build-name` so `PackageInfo.version`
  reports the product version, not the store-submission version. See
  `apps/synapse_app/README.md`.

## [0.2.0] — 2026-05-24

Companion release to Cerebro v0.2.0 — adds the client-side surface for
async councils and mobile push.

### Added

#### Web (Svelte)

- **`@mention` picker** on `ChatInput` for adding human members to async
  councils. Typeahead workspace users from `GET /v1/workspace/users`, plus
  an "Invite by email" fallback row when the @-partial parses as an email.
  Picked humans render as removable chips above the textarea.
- **`MentionPicker.svelte`** — new reusable popover modeled on
  `DirectivePicker.svelte`'s listbox/keyboard semantics.
- **`ToastHost.svelte`** + `toasts` singleton store — fixed bottom-right
  notification stack with click-through to deep links + auto-dismiss TTL.
- **Awaited-user surfacing** — rose-toned "You're awaited" row on
  `/notifications`, "Awaiting you" pip + tinted border on the council list,
  real-time toast on new `awaited_contribution` feed items (polling-based,
  first-poll burst suppressed).
- New types: `WorkspaceUser`, `PendingHuman` (discriminated union of
  workspace + invite variants), `awaited_contribution` FeedItemType.
- New client methods: `listWorkspaceUsers(q, limit)`, `streamChatMessage`
  now accepts a `humans` arg.

#### Flutter

- **`MentionPicker` widget** + `WorkspaceUser` / sealed `PendingHuman`
  models. Chat session detail screen swaps bare `TextField` for the
  picker-enabled input; picked humans render as removable chips above.
- **Push-tap deep linking** — `NotificationService.onCouncilOpen`
  callback funnels FCM `onMessageOpenedApp`, `getInitialMessage`
  cold-start, and local-notification tap paths through one dispatch.
  App shell binds it to `go_router.go('/councils/$councilId')`.
- **`setCurrentTenantId` + tenant filter** — push handlers suppress
  pushes whose `data.tenant_id` doesn't match the currently-signed-in
  tenant (defence-in-depth against stale device-token rows on the
  server side).
- **`push_enabled` preference toggle** on the notifications settings
  screen — separate from the renamed "ntfy fallback" switch since
  Cerebro now gates FCM/APNs independently.
- **`awaited_contribution` feed-item badge** + "AWAITING YOU" pip on
  the council list. Visual language matches the Svelte side.
- **Firebase bootstrap** — `firebase_core` + `firebase_messaging`
  dependencies wired at app start via `initializeFirebase()`. Native
  platform config (`google-services.json`, `AppDelegate.swift` push
  capability) deferred — needs Firebase project + APNs cert provisioned.

#### Backend (Synapse OSS — FastAPI)

- **Mobile-push parity** with the Cerebro Elixir side — new `apns.py`
  + `fcm.py` senders, per-channel dispatcher gating mirroring the
  Cerebro `Synapse.Notifications.DispatchWorker` rewrite.

### Changed

- `ChatInput.svelte` grows a `showMentions` flag (off by default; on
  for the chat-with-tools session screen, off elsewhere).
- `updateNotificationPreferences` accepts optional `pushEnabled`.
- Local-notification payload now carries `tenant_id` so the tap
  handler can re-run the tenant filter at tap time (user may have
  switched tenants between receive and tap).

### Fixed

- Contract parity test `device_token.token_type` updated to accept
  `ntfy + fcm + apns` (previously asserted ntfy-only).

## [0.1.0] — initial tag

Initial release.

[Unreleased]: https://github.com/AstrocyteAI/synapse/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/AstrocyteAI/synapse/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/AstrocyteAI/synapse/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/AstrocyteAI/synapse/releases/tag/v0.1.0
