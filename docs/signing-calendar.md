# Signing calendar (TICK-001, #13)

Free provisioning issues a **7-day** provisioning profile (R-7, D-025). No paid Apple account, so
this cannot be extended — only repeated. When a profile expires the app does not warn, degrade or
explain: tapping the icon does nothing. On a capture day that reads as a broken phone.

## The arithmetic

| Signed | Expires | Demo Day (Sep 9) | Showcase (Sep 10–11) |
|--------|---------|------------------|----------------------|
| 2026-09-02 *(the build now on James's iPhone 17 Pro)* | 2026-09-09 | **NOT covered** | **NOT covered** |
| 2026-09-05 | 2026-09-12 | covered | covered |
| **2026-09-06** | **2026-09-13** | covered | covered |
| 2026-09-08 | 2026-09-15 | covered | covered |

**The build installed on 2026-09-02 expires on Demo Day itself.** Not the day after — the day of.
Whether it survives the morning depends on the hour it was signed, which is not something to find
out on stage.

## Schedule

Under D-036, capture and the live demo run on **one device — James's iPhone 17 Pro (`iPhone18,1`)
with LiDAR**. Its build expiry stops the dataset. There is no standby phone.

His sessions are also the only expensive ones. Emily holds the Mac, James runs Windows and cannot
re-sign unaided, so every install on his handset is two people in one room. That is now the
scheduling risk in this ticket rather than a footnote to it.

| # | Date | Mac owner | Device | Purpose |
|---|------|-----------|--------|---------|
| 1 | 2026-09-02 ✅ | Emily | James's iPhone 17 Pro | Done. Installed and launched. |
| 2 | **by 2026-09-06 — NO DATE AGREED** | Emily | **James's iPhone 17 Pro** | **The session that cannot be missed.** Signed 2026-09-02, so it expires 2026-09-09 — Demo Day itself. Needs co-location, which AC3 requires be agreed in advance. It is not. |
| 3 | 2026-09-08 *(optional)* | Emily | James's iPhone 17 Pro | Top-up before rehearsal. Expires Sep 15. |

**Session 2 is the open item on this ticket.** Every other session is one person at one desk and
can happen whenever. This one needs James and Emily in the same place before Sep 6, and no date has
been agreed. **D-025 fixes the deadline at 2026-09-06 and this document does not move it.**

An earlier draft of this paragraph said Sep 5–8 all produce valid coverage. Sep 7 and Sep 8 do cover
Demo Day arithmetically — a build signed Sep 8 expires Sep 15 — but they leave the app **dead on Sep
7 and Sep 8**, because the build signed 2026-08-31 expires 2026-09-07. That is the gap D-025 exists
to close, and it falls inside the capture window rather than after it. Sep 5 or Sep 6, then.

Widening a locked decision's mandatory date is a decision, not a scheduling detail. If Sep 8 is
genuinely wanted, it needs an amendment in `CHANGES.log` with the two dead days stated.

James's handset is an **iPhone 17 Pro** (`iPhone18,1`); session 2 covers it. Its capability probe
completed on 2026-09-04, so the remaining work is signing and launch verification only.

## Start of every capture day

Launch the app on James's iPhone 17 Pro. Not "check the profile date" — launch it. A
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

Two things can stop this the first time on James's phone, both one-off:

- **Developer Mode** — Settings → Privacy & Security → Developer Mode, then the phone restarts.
- **Trusting the certificate** — Settings → General → VPN & Device Management → Developer App →
  Trust. Until this is done the install succeeds and the launch fails with *"invalid code signature,
  inadequate entitlements or its profile has not been explicitly trusted"*, which reads like a build
  problem and is not.

## What this does not cover

Whether a *re-signed* build preserves data already written to the app's Documents directory.
Re-installing over an existing app normally keeps its container, but nobody has tested it here, and
after #33 James's phone will be holding captures that have not been uploaded yet. **Worth testing at
session 2 with a throwaway capture, before it matters.**
