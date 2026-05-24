# synapse_app

Flutter app for the Synapse multi-agent deliberation product. Targets
mobile (iOS, Android) and desktop (macOS, Windows, Linux) from a single
codebase under `lib/`.

## Versioning

This package has two distinct version concepts — keep them separate:

| Concept | Where | When it changes | Source of truth |
|---|---|---|---|
| **App-store binary version** (`pubspec.yaml`'s `version:` field) | `pubspec.yaml` | Per TestFlight / Play Store submission | Hand-edited |
| **Displayed product version** (e.g. About screen) | Pass `--build-name=` at build time | Per git tag of the synapse repo | `git describe` |

The two intentionally don't have to match: app-store binaries follow
Apple/Google's upgrade-detection cadence (and `+N` build numbers must
monotonically increase), while the product version is the git tag of
the surrounding synapse repo (web + backend + this app ship as one
versioned product).

### Building with the right product version

CI / release builds should pass the synapse repo's tag in via flags:

```bash
flutter build apk \
  --build-name="$(git describe --tags --abbrev=0 | sed 's/^v//')" \
  --build-number="$(git rev-list --count HEAD)"

flutter build ipa \
  --build-name="$(git describe --tags --abbrev=0 | sed 's/^v//')" \
  --build-number="$(git rev-list --count HEAD)"

flutter build macos \
  --build-name="$(git describe --tags --abbrev=0 | sed 's/^v//')"
```

`--build-name` overrides the `MAJOR.MINOR.PATCH` prefix of `pubspec.yaml`'s
`version:` for THIS build only — the file itself is not touched.
`--build-number` overrides the `+N` build-counter suffix; using
`git rev-list --count HEAD` produces a monotonic counter from the
commit history, which satisfies Apple's "build number must increase"
rule across releases.

### Reading the version at runtime

```dart
import 'package:package_info_plus/package_info_plus.dart';

final info = await PackageInfo.fromPlatform();
print(info.version);      // "0.2.0"  (from --build-name)
print(info.buildNumber);  // "1234"   (from --build-number)
```

The values come from the build-time stamping; no env-var injection
required at runtime.

## Local development

```bash
flutter pub get
flutter run                    # auto-picks a connected device / simulator
flutter run -d macos           # force a specific platform
flutter run -d "iPhone 15 Pro" # force a specific iOS simulator
```

For local dev you can ignore the `--build-name` flag — pubspec's
`1.0.0+1` is fine while iterating. Only set it for builds that go
anywhere outside your laptop.

## Testing

```bash
flutter test                    # unit + widget tests
flutter analyze                 # static analysis
dart format --set-exit-if-changed .   # format check
```
