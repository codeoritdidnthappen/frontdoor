# EntryMap — product and interaction design (canon, authored by James, 2026-09-04)

**Precedence:** this document is the authoritative product/interaction spec. `ui-reference-spec.md`
carries the visual tokens, measured decisions, and build notes and defers to this document wherever
the two differ. Reconciliation deltas are listed at the bottom.

---

EntryMap answers one practical question: **"Can I use this entrance with my specific needs?"**

It does not grade businesses, make legal claims, or reduce accessibility to wheelchair access. It
shows visually observed entrance features, how recently they were seen, who reported them, and how
confident the evidence is.

## Who uses it

One app, three levels of participation:

| User | What they can do |
|---|---|
| Guest | Browse, search, apply temporary My Needs filters, inspect evidence, use list view |
| Signed-in community member | Save needs, scan entrances, suggest corrections, save businesses, receive updates |
| Business owner | Everything above, plus claim and maintain their entrance through the My Business workspace |

There is no separate "disabled user" mode. The public and disabled experiences are merged; optional
My Needs filters personalize the same map. Owners use the same app: before approval they see a claim
submission flow; after approval that area becomes their owner workspace.

## Primary navigation

Bottom navigation contains only: **Map · Scan · Profile**. Map and Profile use violet active states.
Scan is the prominent center action with a marigold accent ring — not a large yellow block. The app
opens on the map whenever onboarding is complete.

## Launch and onboarding

1. **Splash** — deep-aubergine screen with the EntryMap symbol and wordmark (*entry* in sky blue,
   *map* in white). The logo gently resolves into the map; reduced motion uses a static transition.
2. **Welcome** — "Access starts before you arrive. Find entrances and places that fit your needs."
   Actions: Sign in · Continue as guest. Guest use remains fully functional for browsing.
3. **Location permission** — benefit before the OS prompt: "See what works nearby. We use your
   location to center the map and show distance." Actions: Allow location · Choose an area instead.
   Denying permission never creates a dead end.
4. **My Needs setup** — optional: Wheelchair · Cane/walker · Low vision · Limited grip · Stroller.
   Multi-select, skippable, editable later. The screen explains these choices change match
   information — not which businesses are allowed to appear.

## Main map

**Before My Needs:** all three trust-tier pins, no match halos; a floating My Needs control invites
personalization without blocking exploration. Map style: luminous low-detail street geometry, white
streets and approaches, pale blue/lavender buildings, aubergine street labels, white sheets and
cards, pale-lavender surrounding interface.

**After My Needs:** every pin gains an outer match halo — Good (solid) · Partial (dashed) · Unknown
(dotted). Line style always carries the state, even in grayscale. The halo is visibly separated from
the trust ring so "match" is never confused with "evidence quality." There is never a negative or
failing state: Partial = some relevant features were observed; Unknown = more information needed.

**Controls:** drag, pinch or accessible zoom buttons, current location, search (business / address /
neighborhood), map ⇄ accessible list toggle, My Needs, the "How trust grows" legend. Dense clusters
show only a place count — never an averaged trust score; tapping zooms into individual pins.

## Trust-tier pins (exactly three)

- **Estimated** — hollow pin, dashed outline, soft blue, small italic *i*, no checkmark. "Early
  information that has not yet been photographed on-site." An invitation, never a poor grade.
- **Scanned on-site** — solid marigold pin, person icon, two of three ring segments filled, slightly
  larger. "A community member photographed the entrance in person." The trust workhorse.
- **Owner-confirmed** — solid violet pin, storefront icon, three of three segments, separate outlined
  check, slightly larger again. "The business owner has attested to the current entrance
  information." Never called "verified"; never a shield.

Pins only upgrade; aging information gets a freshness message, never a downgrade or warning state.

**"How trust grows":** a clean white pop-up showing the three pins in order with short descriptions:
"More direct sources strengthen the information. Trust can grow as neighbors scan and owners
confirm." Tiers are informational and never appear in Filters. No fourth/auditor tier is displayed
anywhere.

## Finding a business

**Search:** full-width field with recent searches and nearby suggestions; results group multiple
entrances under one business; show distance and relevant feature matches; trust shown by tier pin,
not stars; accessibility never summarized as a single score. Selecting centers the entrance and opens
its card.

**List view:** a non-map equivalent — business name, entrance name/street, trust tier, match status,
freshness, distance, confirmed features. Supports screen readers, larger text, and map-averse users.

## Selecting a pin

Tap → pin enlarges slightly, halo strengthens, light haptic, bottom-sheet preview opens, pin stays
visible above the sheet. Sheet positions: **Peek** (name, tier, match) · **Medium** (key features,
freshness) · **Full** (all evidence and actions). Drag, tap handle, or swipe down.

## Business and entrance card

Each real-world entrance has its own card (a business with two entrances has two pins, two evidence
records). Contents: business name, entrance location, trust tier, match status, freshness,
confidence, feature chips, provenance summary, Directions, Save, Suggest a correction.

**Feature chips:** Step-free entry · Ramp visible · Auto door button · Easy-grip handle · Wide door ·
Accessibility signage · Clear approach. A chip appears confirmed only when visible in evidence; the
app never infers "ADA compliant." Each chip: name, "Seen…" freshness, small confidence indicator,
tap affordance. Unknown features: "Not yet seen — be the first to scan." in white/lavender — never
gray, red, or warning imagery.

**Evidence receipts:** every chip and trust badge opens one — source photograph, date, capture
method, freshness, confidence, provenance lines, Suggest a correction. "Photographed Tuesday · 4
neighbors, 1 owner." Independent evidence stacks: "Reported accessible on OpenStreetMap · 2024" /
"Texas accessibility inspection on record · 2019." **The Texas flag appears beside the state-record
line only** — it does not alter the pin tier, behave like an owner check, or imply certification.

**Confidence** = strength and agreement of evidence, not how accessible the entrance is: one bar/dot
(limited evidence) · two (multiple observations) · three (independent sources agree). The receipt
explains the level.

**Freshness** always describes time: Fresh today · Seen 3 weeks ago · Scanned 8 months ago ·
"Scanned 14 months ago — help us re-check." Older evidence shifts to muted amber; never red; never
"bad" or "unsafe."

## My Needs filters

Bottom sheet: saved needs profile first (temporary add/remove without overwriting the saved
profile); feature filters (Step-free, Wide door, Easy-grip handle, Auto door button, Clear approach);
Distance, Freshness, Open now. **Trust tier is never a filter.** Primary action shows the count:
"Show 12 entrances." Active filters appear as removable chips above the map; clearing filters does
not clear the saved profile.

## Live scan — the signature interaction

1. **Introduction** — "Help map an entrance. A quick scan helps neighbors plan ahead." Explains:
   capture only the entrance; include the path from sidewalk to door; avoid faces and license plates.
2. **Camera permission** — plain-language primer before the system prompt. If denied: Open settings ·
   Choose an existing photo · Return to the map.
3. **Doorway capture** — large framing guide around the complete entrance; prompts one at a time:
   Center the full doorway · Include the approach · Step back a little · Hold steady. Capture button:
   white center, aubergine camera icon, marigold ring.
4. **Processing (~7 s, never over 8)** — 0–1.0 s image settles · 1.0–2.5 "Doorway framed" ·
   2.5–4.0 "Entry path visible" · 4.0–5.5 "Photo quality checked" · 5.5–6.5 detected chips populate ·
   6.5–7.5 pin drops with bounce and ripple. Ring advances smoothly; restrained haptic per check, one
   stronger friendly haptic at landing. Reduced motion: skip countdown/bounce/ripple, present results
   immediately with a screen-reader announcement.
5. **Review** — photo, entrance location, features visually identified, anything still unknown. The
   user may remove an incorrect suggested feature; never asked to declare legal compliance. Actions:
   Retake · Publish scan. Guests sign in here; the draft is preserved.
6. **Pin landing** — new Scanned on-site pin lands, two segments fill, soft ripple, card opens, chips
   animate in sequence. "Scan published. Thanks for helping your neighbors plan ahead."

## Corrections

Every claim has Suggest a correction: What changed? · Which entrance? · What did you notice? · Add a
photo. A correction does not erase earlier evidence — it becomes another dated source and enters
review. When sources disagree, the receipt shows both, says information differs, and invites a new
scan; no red, no blame.

## Empty area / stale evidence

Empty: "No entrances mapped here yet. Be the first to help neighbors plan ahead." — Scan an entrance ·
Try another area. Never apologizes. Stale (contextual, infrequent): "Could you take another look?
Last scanned 14 months ago. A fresh photo helps everyone plan with confidence." — Re-check entrance ·
Maybe later.

## Profile

My Needs · Saved entrances · My scans · My corrections · Location settings · Text size · High
contrast · Reduce motion · Privacy · Notifications · Sign-in status · For business owners. Guests
configure accessibility locally; signing in syncs across devices.

## Owner experience

**Invitation (in Profile):** "Claim your door — get scanned, get seen. Accessibility fixes may
qualify for federal tax credits — ask your accountant." → Start a claim.

**Claim flow:** search business → select the exact entrance → confirm role and contact → choose
business email or phone confirmation → confirm authorization → submit → track status (Submitted ·
Business matched · Ownership review · Workspace ready). Before approval a tracker; after approval,
My Business.

**My Business:** view public listing, update visible entrance features, add/replace photos, add
visitor notes, review freshness and confidence, see community scans, respond to corrections. Owners
edit their own observations; they cannot rewrite community evidence or state records. Publishing adds
"Owner update · today." The pin becomes Owner-confirmed only when attestation requirements are
complete. Owner photos: full entrance · sidewalk-to-door approach · hardware/button; review catches
likely faces and plates and asks to replace or crop.

## Offline, notifications, motion, accessibility

**Offline:** photo and draft stay encrypted on-device, "Saved for later," upload resumes on
connectivity, map available from cache; nothing silently lost.

**Notifications:** optional, grouped — saved entrance updated · correction received a response · a scan
needs clarification · owner claim changed status · nearby entrance needs re-checking. No streaks,
guilt messages, or public leaderboards.

**Motion:** lively but trustworthy — pins squash slightly on tap; selected pins rise 4–6 px; sheets
use soft spring motion; filter chips compress gently; trust-ring segments fill clockwise; scan
completion is the largest motion moment; everyday navigation stays calm. All states understandable
with motion disabled.

**Accessibility:** body text targets 7:1; controls at least WCAG AA; touch targets ≥44×44 (48
preferred); nothing relies on color alone; dynamic text never truncates claims; VoiceOver/TalkBack
announce business, entrance, tier, match, freshness; every map result available as a list; pin icons
distinct in grayscale; visible focus; reduced motion respected; photos carry useful alt text;
language factual and nonjudgmental.

## Complete screen inventory (44)

1 Splash · 2 Welcome/sign-in · 3 Location primer · 4 My Needs onboarding · 5 Map without My Needs ·
6 Map with match halos · 7 Search · 8 Search results · 9 Accessible list view · 10 Filter sheet ·
11 How trust grows · 12 Pin-card peek · 13 Expanded entrance card · 14 Feature receipt · 15 Full
evidence receipt · 16 Unknown-feature invitation · 17 Suggest a correction · 18 Correction submitted ·
19 Empty area · 20 Stale evidence/re-check · 21 Scan introduction · 22 Camera permission · 23 Camera
capture · 24 Scan processing · 25 Scan review · 26 Scan published · 27 Offline scan saved · 28 Profile
· 29 Saved entrances · 30 My contributions · 31 Accessibility settings · 32 Notification settings ·
33 Owner invitation · 34 Find your business · 35 Select an entrance · 36 Confirm ownership · 37 Claim
submitted · 38 Claim status · 39 My Business overview · 40 Edit entrance · 41 Manage entrance photos ·
42 Owner update review · 43 Owner update published · 44 Public-listing preview.

---

## Reconciliation deltas vs `ui-reference-spec.md` (this document wins)

- **Texas/state record:** flag beside the receipt line ONLY. The pin-shoulder lone-star accessory and
  the "State records" map layer toggle in the spec's pin hierarchy are withdrawn.
- **Card sheet:** three positions (Peek / Medium / Full) — the spec's single bottom sheet is now the
  Full position.
- **Location primer:** second action is "Choose an area instead" (spec had "Not now").
- **Processing sequence:** timings per this document (image settle → three checks → chips populate →
  pin drop); the shipped self-drawing ring keeps its motion but re-times to these beats, with chips
  populating before the review/landing moment.
- **New surfaces the spec lacked:** splash, search + results, accessible list view, clusters, Save,
  Directions, notifications policy, offline draft, Reduce Motion toggle in Profile, My corrections,
  Saved entrances, public-listing preview.
- Everything else in the spec (tokens, measured capture-mode decisions, evidence-decay model,
  multi-need stacking, proof-of-control mechanics, processing design bar) remains in force.
