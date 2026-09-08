# EntryMap — UI reference spec (visual tokens + measured decisions)

> **Precedence:** `product-interaction-design.md` (James, 2026-09-04) is the authoritative product and
> interaction spec. This file carries tokens, measured decisions, and build notes and defers to it
> wherever they differ; see its reconciliation list.

Derived from James's chosen reference mock (save the image alongside this file).
This supersedes the exploratory pages (`map-ui-directions.html`, `map-ui-hybrids.html`);
those remain as archives.

## Design tokens

- **Ground**: soft lavender/periwinkle map canvas (#EDEBFA-ish), white cards, generous
  radius (~16px), airy spacing. Buildings pale, streets white, trees dotted blue.
- **Accents**: marigold (scan/action + Scanned tier), purple (Owner tier + links/actions),
  soft blue (Estimated tier + feature icons), teal/green reserved — see rules below.
- **Type**: rounded humanist sans throughout (reference uses a single family; the
  editorial-serif option from Field Notes was not carried into the reference).
- **Nav**: bottom bar Map · **Scan** (center: outlined circle with camera glyph, marigold
  ring — the v2 treatment, James's pick 2026-09-03) · Profile.

## Trust tiers (three, fixed wording)

| Tier | Pin | Notes |
|---|---|---|
| Estimated | hollow pin, dashed blue outline, italic ⓘ | never gray, never reads negative |
| Scanned on-site | solid marigold pin, person glyph, segmented ring | the trust workhorse |
| Owner-confirmed | solid purple pin, storefront glyph, OUTLINED check floating beside | no shield, never "verified" |

- Pins only upgrade. No negative state exists anywhere.
- Match halo when a needs profile is set: labeled chip ("Good match") + halo;
  good=solid / partial=dashed / unknown=dotted (line style + color, never color alone).

## Pin hierarchy — one pin, one message (James's correction, 2026-09-04)

The map answers ONE question at a time; accessories that pile up on pins are
banned. Strict layering:

- **Level 0 — the pin IS the tier** (always, and nothing else by default):
  silhouette + tier treatment only. The owner-confirmed check is INTEGRATED into
  the pin design (a notch/badge within the silhouette), never floating beside it.
- **Level 1 — one accessory slot, maximum one mark**, by priority:
  1. Needs profile active → the MATCH HALO takes the slot (fit is now the map's
     message; tier stays readable but secondary).
  2. (withdrawn) — the former state-records layer/lone-star accessory is removed per the
  product doc; the accessory slot holds the match halo only.
- **Level 2 — card only, never on map pins**: sparkle/AI glyph, Texas tab,
  neighbor counts, freshness, provenance of any kind. These render as card rows
  and receipt content.
- **Label chips ("Good match")**: only on the SELECTED pin and the top nearby-
  match card — never on every matching pin.
- Zoom rule: below full zoom, even Level 1 simplifies (halo tint only, no
  outline style) — legibility beats completeness at distance.

## External-data accessories

- **TABS/state record**: WITHDRAWN from pins (product doc 2026-09-04) — the Texas flag
  appears beside the state-record receipt line ONLY; it never alters the pin, never sits
  on the pin shoulder, and there is no state-records map layer.
- Other sources (OSM etc.): provenance rows on the card only, each with source glyph,
  label, and date. External data never fills ring segments or chips.

## Card anatomy (bottom sheet, top to bottom)

1. Tier avatar + business name + tier chip.
2. Two tiles: **Freshness** ("2 days ago", clock icon — ages to muted amber, worded
   about time) and **Confidence** ("High" + dot-triple).
3. Provenance rows (receipts): camera row "Photographed Tuesday — 4 neighbors, 1 owner",
   then external-source rows. Every row opens its receipt (photo/date/method).
4. Feature chips: icon + feature name + dot-triple confidence (●●○). Named by what was
   seen ("Step-free entry", "Wide door", "Easy-grip handle") — never legal claims.
5. Unknown row: "Not yet seen — be the first to scan." (invitation, not apology).
6. "Suggest a correction" (purple, pencil icon) — on every card.
7. Buttons: **My needs** (heart) · **How trust grows** (the trust-explainer page).

## Color rules (resolved tensions)

- **Green is reserved for match state** ("Good match" chip) and nothing else — confidence
  dots use the tier's own hue or neutral teal, NOT green, so green never leaks toward
  "verified accessible" semantics.
- Amber = freshness aging only. Red does not exist in the product.

## Evidence decay (per-criterion, not per-photo — James's correction, 2026-09-04)

Evidence ages by what it shows, gated by tenant turnover, not by the calendar alone:
- **Structural criteria** (step-free, ramp, rails, door width): long half-life — years.
  A dated photo of an unaltered building is valid structural evidence.
- **Tenancy-coupled criteria** (signage, hardware, clear approach, the business itself):
  short half-life — months.
- **Turnover gate**: place_id business_status + Austin certificate-of-occupancy records
  detect tenant change at an address. Older imagery keeps structural weight while no
  turnover is detected; a turnover event demotes ALL of that address's imagery-derived
  evidence to needs-recheck (internally — publicly the pin simply invites a fresh scan).
- Freshness amber thresholds therefore differ per chip class; every line still shows
  its actual date.

## Processing feedback — always animated, always named (James, 2026-09-04)

Every moment the app is working shows visible progress with NAMED steps — never a
bare spinner, never a frozen screen. The user should always be able to read what
is happening:
- **Scan processing**: the ~7s ring with the three named checks (Doorway framed ·
  Entry path visible · Photo quality checked), "Usually under 8 seconds."
- **Double-check (agreement gating, verified tier)**: when a second model pass runs,
  the ring gains a fourth named step — "Double-checking" — and the caption updates
  ("Usually under 15 seconds"); the extra wait is explained, not hidden.
- **Publish**: upload + storage shows "Saving your scan…" with the pin-drop animation
  as the completion state.
- **Map / data loads, claim submission, photo upload in the workspace**: skeleton or
  progress states with a one-line label of the step.
- All of it collapses to a simple progress bar under Reduce Motion; none of it may
  block the bottom nav.
- **Design bar: stunning yet simplistic.** One elegant motion idea executed
  perfectly — not layered effects. The ring is the hero; steps tick in with a
  single satisfying transition; no particle confetti, no spinners-on-spinners, no
  copy that shouts. It should feel calm and certain on a projector at 30 feet and
  on a phone at arm's length.

## Signature animation (live scan)

Photo in → ~7s processing (progress ring, checklist items ticking in one by one) →
pin drops with bounce + ripple, chips populated, counter ticks. Under 8 seconds;
prefers-reduced-motion collapses to end state.

## Onboarding & profile (canon from the "universal access" boards, 2026-09-04)

- **Guest-first**: "access starts before you arrive" welcome → **Sign in** OR
  **Continue as guest**; the guest path stays fully usable and guest choices stay
  on this device. Signed-in profiles sync; guests stay local. (Account model L1/L2
  made concrete.)
- **Location permission**: plain-language primer BEFORE the OS prompt ("We use your
  location to center the map and show walking distance"), with **Not now** as a
  real option and "You control this in Settings."
- **My Needs picker**: optional, "choose any that help" — Wheelchair · Cane/walker ·
  Low vision · Limited grip · Stroller (exactly the researched personas), Continue /
  Skip for now. Needs are editable any time from Profile.
- **Multi-need profiles (canon, 2026-09-04)**: selected needs STACK — the active
  checklist is the union of each selected persona's critical features, deduped.
  The map halo shows the COMBINED verdict (weakest link: good only when every
  critical feature for every selected need is confirmed; partial/unknown
  otherwise) — one message on the map. The CARD carries the per-need breakdown
  ("For wheelchair access: 3 of 3 · For low vision: 1 of 2 — signage not yet
  seen"), and match-card arithmetic ("N of M needs") uses the combined, deduped
  M. Presence-features stack monotonically (no contradictions); the one real
  preference tension (e.g. a cane user preferring one step + rail over a long
  ramp) is handled by per-persona feature toggles after selection, never by the
  combined-verdict logic guessing.
- **Profile screen**: avatar, guest-vs-signed-in state ("Sign in to save"), My Needs
  chips with edit, Location toggle, **Text size**, **High contrast**, Privacy.
- **Accessibility floor (product-wide)**: 44px touch targets, 7:1 text contrast.

## Discovery & filters (same boards)

- **Universal map first**: the map with legend (three tiers) is the landing surface;
  no login gate anywhere before it.
- **Filter sheet**: My Needs chips + **Entrance features** (Step-free, Wide door,
  Easy-grip) + **Freshness** (Any / 7 days / 30 days) + **Distance** slider +
  **Open now** toggle → "Show N places" button. NO trust-tier facet — filters
  describe needs, never trust tiers. Guests can filter now (temporarily);
  sign in to save filters.
- **Nearby matches**: photo result cards with match arithmetic in plain words —
  "Good match" / "**3 of 3 needs**" + distance. Fit, not certainty.
- **Evidence receipt**: its own card — camera row, "4 neighbors", "1 owner",
  "Texas record · <year>", footer "Sources, dates, and confidence — not a badge."
- **Open-now caveat (implementation)**: hours data comes from the place provider at
  display time (Google ToS: not storable) — the toggle works live-only.

## Community scanning flow (canon from the community boards, 2026-09-04)

- **Camera permission primer**: "Help map an entrance — a quick 7-second scan helps
  neighbors plan ahead" + the privacy line "**Only the doorway is captured.**"
  Allow camera / Not now.
- **Capture guidance**: full-doorway frame guide with live coaching chips ("Center
  the full doorway", "Step back a little") — the protocol's framing rules turned
  into UI instead of instructions.
- **Processing**: the ~7s ring with named, human steps — Doorway framed · Entry
  path visible · Photo quality checked — "Usually under 8 seconds." Reduce Motion
  collapses to a simple progress state.
- **Review first, publish second**: the user sees their capture (the BLURRED
  rendering — this screen doubles as privacy verification) + "Visually confirmed"
  chips, then chooses **Retake** or **Publish scan**. Nothing publishes without
  this consent gate. Confirmation: "Scan published — thanks for helping your
  neighbors" + the tier legend.
- **Empty areas invite**: "No entrances mapped here yet — be the first to help
  neighbors plan ahead" → Scan an entrance / Try another area. Invite, don't shame.
- **Suggest a correction** (form anatomy): business header → "What needs updating?"
  dropdown → 300-char "What did you notice?" → optional photo → "We'll review your
  note with the community." Corrections stay human.
- **Re-check nudges**: staleness drives a gentle ask — "Could you take another
  look? Last checked 11 months ago" (muted amber clock; age is context, not
  failure) → Re-check entrance / Maybe later.
- **Every state has a next step**: offline → "Saved for later — your scan uploads
  when you're back online; keep exploring"; camera denied → "Turn it on when
  you're ready" + Open settings; location denied → "Search the map" without
  sharing location. Muted amber communicates time only; system states stay calm
  and neutral.

## Owner experience (canon from the business-owner boards, 2026-09-04)

**Claim flow (Start → Find → Confirm → Track):**
- Owner tools live in **Profile** ("For business owners" → Claim your door card with
  the tax-credit line → Start a claim). The user's own scans list sits beside it.
- **Find**: search, then "choose the entrance you manage" — disambiguates multiple
  locations of the same business (entrance-level, not business-level, claims).
- **Confirm**: role dropdown (Owner/Manager — surface-control honesty), work email +
  business phone fields, verification choice (Business email link / Call the
  business), an explicit "I'm authorized to manage this business listing" checkbox,
  and the secure-verification reassurance line.
  **GUARDRAIL (spec overrides mock literalism): the typed contact is input, not
  authority — codes are only ever sent to a contact matching the independently
  resolved business domain or listed phone; an arbitrary personal address fails
  validation.** (Proof-of-control invariant upheld.)
- **Track**: visible claim timeline — Submitted ✓ → Business match ✓ → Ownership
  review (in progress) — with "we'll email you when your workspace is ready" and an
  Owner-confirmed preview. Progress stays visible; expectations set.

**Owner workspace (Overview → Edit → Photos → Receipt):**
- Overview: tier state, entrance features with checks, freshness ("Updated today"),
  confidence, **community contribution count** (community scans shown beside owner
  data, never replaced by it), Edit entrance / Manage photos.
- Edit: "**Update only what you can see at the entrance**" — feature dropdowns are
  Yes / No / **Not sure** (owner abstention is honest too); a 200-char "What should
  visitors know?" free-text (door weight, buzzer location — the not-photo-assessable
  facts get their honest home here); **state records render read-only-locked** —
  owners edit observations, not state records.
- Photos: "Show the full path from sidewalk to door"; primary photo; JPG/PNG ≤10MB;
  review checklist ("2 photos ready", "Avoid faces and license plates" — guidance on
  top of the automatic blur, not instead of it); Publish update.
- Receipt: "Update published" with provenance **stacked and legible** — Owner update
  · today / Scanned on-site · 4 neighbors / Texas record · read-only — plus the
  tax-credit link and "View public listing." Owner data joins the stack; it never
  collapses it.

## Capture modes — decided by the 2026-09-04 held-out experiments (James's call)

Two modes only:
1. **Photos for verification** (the Scan screen): one normal-lens photo yields an honest
   partial checklist (100% committed / 79% coverage measured); five or six views yield
   the verified result (97% / 90% held-out on 52 unseen doors). Ultra-wide loses to a
   normal single (96% / 75%) — the one-photo instruction stays "the whole door, normal
   lens." Walk-up video is dominated by a single photo (100% / 57%) and is dropped.
2. **Walk-by video for coverage** (a separate "map your block" contributor mode): one
   continuous portrait pass of a block face, auto-segmented per storefront, feeding the
   Estimated tier — 82% commit rate vs 20% for Street View on the same engine. Short
   multi-door clips are the same mechanism at small scale (93% / 75%), folded in.
   Door inventory comes from the frames, never the walker's memory.

## Baked-in elements beyond the mock (all previously agreed — required, not optional)

1. **Map layers**: a "State records" toggle lighting every TABS-matched pin at once
   (the demo beat), and the **route layer** — Austin curb-ramp/sidewalk condition as
   corner markers + path shading between user and door ("Curb ramp at corner ·
   condition B · City of Austin").
2. **My-needs picker**: one-time, skippable profile (wheelchair · cane/walker · low
   vision · limited grip · stroller); persona seeds default feature weights from the
   researched persona-feature matrix, individually tunable. Once set, pins show
   good/partial/unknown match halos and cards re-highlight the chips critical to
   THAT persona. Trust tier is never a filter facet.
3. **Estimated-tier CTA**: its provenance line always ends with the replacement
   invitation — "Estimated by AI from street imagery · <date> — been here? Confirm in
   30 seconds." The AI glyph is the sparkle ✦ with a dashed circle. The estimate
   visibly wants to be replaced; that is the growth loop.
4. **Scan accepts whatever the user has**: in-app camera, camera-roll upload, 1 photo
   or 6. One photo yields an honest partial checklist; when coverage is thin the app
   asks "got it — one more photo from further back?" instead of guessing. A disabled
   user who can only upload one photo is a first-class citizen.
5. **Owner funnel**: "Claim your door" banner — get scanned, get seen; missing-feature
   fixes "may qualify for federal tax credits — ask your accountant" (Section 44/190,
   never stated as tax advice). Owner/verified-tier captures are in-app only with
   time+location attestation (anti-staging); camera-roll uploads cannot earn the
   owner tier.

   **Claim flow (canonical, per James 2026-09-03):**
   Public map → "For business owners" → Claim your door → find & select business →
   submit ownership confirmation → pending review → approved → **My business workspace**.
   - Ownership confirmation options (GBP-style): call/text to the number already on
     the public listing, email at the business domain, or an in-store-delivered code
     entered from the workspace. Demo scale: "pending review" = manual approval by us;
     the flow is unchanged when it automates.
   - **Proof-of-control mechanics**: the claimant NEVER supplies the contact point —
     we resolve the business's canonical phone/domain from independent public sources
     and deliver a one-time code there; the claimant only proves receipt. Backstops:
     every claim passes human review before approval; the Owner-confirmed ring still
     requires the attested at-the-door capture (a wrong approval cannot fabricate
     data); claims are revocable on dispute with no public trace. Honest limit:
     channels verify control of the business's communication surface, not legal
     ownership — acceptable because this tier is attestation, not independence.
   - A claim NEVER changes the public pin by itself — only the workspace's attested
     capture can earn the Owner-confirmed ring.
   - Workspace contents: the pin as customers see it, claim status, the guided
     capture flow, correct/dispute channel, tax-credit explainer.

   **Account model (three levels):**
   - Browse: no login, ever. The map and every receipt are anonymous-readable.
   - Contribute (scan, correct): lightweight account — Sign in with Apple or email
     magic link (Apple required on iOS if any third-party login is offered). Accounts
     give scans provenance: "4 neighbors" = four distinct accounts.
   - Claim: same login + the ownership confirmation channel. **Login says who you
     are; it never says what you own** — the proof is always the confirmation step.
     One account can own multiple doors; the workspace is a list.
6. **How trust grows** page: the tier ladder explained with receipts philosophy
   ("every badge opens into its evidence"), method + error-rate disclosure lives here
   once (Zestimate pattern), and the roadmap line: "as licensed accessibility
   specialists join, a fourth ring lights up."
7. **Privacy is invisible but stated**: faces are auto-blurred and GPS is stripped at
   upload; a one-line note in the scan flow says so. Frames where a face survives
   blur are auto-quarantined without costing the door its verdict — the user never
   performs a privacy step.
8. **Freshness guard on identity**: pins resolve to live place_ids; a business Google
   marks closed gets its pin retired from public view (never shown as a negative —
   it simply leaves the map).
9. **Disagreement handling**: when sources conflict (AI vs OSM vs owner), the card
   shows the neutral form only ("owner reports X; a scanner measured Y — help us
   re-check"); disagreements otherwise stay internal as scan priorities.
10. **Language rules everywhere**: features not legal claims; "not visible" never
    rendered as "absent"; wording about time, never about the place; no red, no
    public negative state, anywhere, ever.
