# Signing calendar (TICK-001, #13)

Free provisioning issues a **7-day** provisioning profile (R-7, D-025). No paid Apple account, so
this cannot be extended — only repeated. When a profile expires the app does not warn, degrade or
explain: tapping the icon does nothing. On a capture day that reads as a broken phone.

## The arithmetic

| Signed | Expires | Demo Day (Sep 9) | Showcase (Sep 10–11) |
|--------|---------|------------------|----------------------|
| 2026-09-02 *(the build now on both phones)* | 2026-09-09 | **NOT covered** | **NOT covered** |
| 2026-09-05 | 2026-09-12 | covered | covered |
| **2026-09-06** | **2026-09-13** | covered | covered |
| 2026-09-08 | 2026-09-15 | covered | covered |

**The build installed on 2026-09-02 expires on Demo Day itself.** Not the day after — the day of.
Whether it survives the morning depends on the hour it was signed, which is not something to find
out on stage.

## Schedule

Both verified capture devices (iPhone 16, iPhone 15 Pro Max) and the build Mac are held by **Emily**,
so sessions 1 and 2 are one person at one desk. No co-location to arrange, which is what made this
a scheduling risk in the original ticket.

James's phone is the exception, and the exception is now proven rather than assumed: a build was
installed and launched on it on 2026-09-02. That is the AC1 criterion met on a third device, and it
means a re-sign for his handset is a real session with two people in it, not a hypothetical.

| # | Date | Mac owner | Devices | Purpose |
|---|------|-----------|---------|---------|
| 1 | 2026-09-02 ✅ | Emily | iPhone 16, iPhone 15 Pro Max | Done. Both launched and ran the capability probe. |
| 2 | **2026-09-06** | Emily | iPhone 16, iPhone 15 Pro Max | **Required.** Covers Demo Day and the Showcase to Sep 13. |
| 3 | **before he next captures** | Emily | James's iPhone 17 Pro | **Requires both people present.** His build was signed 2026-09-02 and expires with the others. |
| 4 | 2026-09-08 *(optional)* | Emily | whichever device demos | Top-up only if session 2 slipped. Expires Sep 15. |

Session 2 is the one that cannot be missed. **D-025 fixes the deadline at 2026-09-06 and this
document does not move it.**

An earlier draft of this paragraph said Sep 5–8 all produce valid coverage. Sep 7 and Sep 8 do cover
Demo Day arithmetically — a build signed Sep 8 expires Sep 15 — but they leave the app **dead on Sep
7 and Sep 8**, because the build signed 2026-08-31 expires 2026-09-07. That is the gap D-025 exists
to close, and it falls inside the capture window rather than after it. Sep 5 or Sep 6, then.

Widening a locked decision's mandatory date is a decision, not a scheduling detail. If Sep 8 is
genuinely wanted, it needs an amendment in `CHANGES.log` with the two dead days stated.

James's handset is an **iPhone 17 Pro** (`iPhone18,1`), not the iPhone 16 Pro the team audit
recorded. Session 3 covers it. Its capability probe has still not been run, so it is signed but
unproven as a capture device -- see TICK-020 (#24).

## Start of every capture day

Launch the app on each device that is going out. Not "check the profile date" — launch it. A
profile can be revoked or invalidated for reasons other than expiry (Apple ID re-auth, device
re-pair, a Mac that has forgotten the certificate), and launching is the only check that covers all
of them.

If it does not launch: re-sign before leaving. A capture day lost to signing is a whole day of
entrances, and there are not many left.

This is a start-of-day step and it now lives where operators actually read it:
[capture-protocol.md](capture-protocol.md), in the pre-departure section and the door checklist.
(An earlier draft said #64 "is still unwritten" and kept the check here instead. #64 is written and
merged, so the check was sitting in a document no field operator opens.)

## Re-signing, step by step

From the repository root with the device connected and unlocked:

```
cd ios && xcodegen generate
xcodebuild -project FrontdoorCapture.xcodeproj -scheme FrontdoorCapture \
  -destination 'platform=iOS,id=<device-udid>' \
  -derivedDataPath /tmp/fd -allowProvisioningUpdates \
  DEVELOPMENT_TEAM=<team-id> build
xcrun devicectl device install app --device <device-udid> \
  /tmp/fd/Build/Products/Debug-iphoneos/FrontdoorCapture.app
xcrun devicectl device process launch --device <device-udid> com.frontdoor.capture
```

`xcrun devicectl list devices` gives the UDIDs. `DEVELOPMENT_TEAM` is the personal team id from the
signing certificate; it is deliberately not committed (D-025), because it differs per Apple ID.

Two things that will stop this the first time on a given phone, both one-off:

- **Developer Mode** — Settings → Privacy & Security → Developer Mode, then the phone restarts.
- **Trusting the certificate** — Settings → General → VPN & Device Management → Developer App →
  Trust. Until this is done the install succeeds and the launch fails with *"invalid code signature,
  inadequate entitlements or its profile has not been explicitly trusted"*, which reads like a build
  problem and is not.

## What this does not cover

Whether a *re-signed* build preserves data already written to the app's Documents directory.
Re-installing over an existing app normally keeps its container, but nobody has tested it here, and
after #33 the phones will be holding captures that have not been uploaded yet. **Worth testing at
session 2 with a throwaway capture, before it matters.**
