# Frontdoor capture app

The instrument for the whole dataset (D-014). AVFoundation + CoreMotion, and **no AR session is
ever started** — that is how the method boundary in D-015 is enforced by construction rather than
by discipline.

At TICK-021 this is a scaffold: camera preview, a shutter, and one photo. Everything the app
eventually records — intrinsics, gravity, depth, entrance ID and caliper reading, ROI taps, the
shot list, the sidecar, upload — is TICK-022 to TICK-029.

## Build

The `.xcodeproj` is **generated, not committed**. A `.pbxproj` is a merge-conflict generator and
four people work in this repo, so `project.yml` is the source of truth.

```
brew install xcodegen        # once
cd ios && xcodegen generate
open FrontdoorCapture.xcodeproj
```

Simulator build, no signing needed:

```
xcodebuild -project ios/FrontdoorCapture.xcodeproj -scheme FrontdoorCapture \
  -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
```

The simulator supplies neither a camera nor device motion, so the app correctly shows its
"cannot capture" state there. That exercises the degradation path; it does not exercise capture.
Capture is only verifiable on hardware.

## On device

Free provisioning (D-025, TICK-001): open the project, set your own Apple ID under Signing &
Capabilities, and run to James's cabled iPhone 17 Pro. `DEVELOPMENT_TEAM` is deliberately not committed
because it differs per team member.

Builds signed this way **expire after 7 days**. TICK-001 owns the signing calendar; a re-sign no
later than 2026-09-06 is mandatory so the build survives Demo Day.

## The ARKit boundary

Enforced twice, because the Xcode phase only runs on a Mac:

- `Scripts/assert-no-arkit.sh` — an Xcode pre-build phase, fails the build.
- `tests/test_ios_no_arkit.py` — runs in CI on Linux, so every pull request is checked even
  though the runner has no Xcode. It also runs the shell script against fixtures, so the two
  guards cannot drift apart.

## Layout

```
FrontdoorCapture/
  App/       app entry
  Capture/   AVFoundation session, CoreMotion, availability states
  UI/        preview and shutter
```

`Capture/` is the whole capture surface. Rendering (EPIC-03, TICK-063) observes `CaptureController`
and adds views alongside `UI/`; it does not reach into the session. That is the structural
mitigation for R-11 — the Demo Day app cannot drift from the characterised capture path because
there is only one path.
