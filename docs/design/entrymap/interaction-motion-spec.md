# EntryMap interaction and motion specification

Motion explains what changed, where it went, and what the person can do next. It is never used only as decoration.

## Principles

- Keep ordinary feedback between 90 and 320 ms.
- Reserve the theatrical moment for the live scan and pin drop.
- Preserve spatial continuity between a pin, its business sheet, its feature chips, and their receipts.
- Never recolor a trust pin to communicate selection, matching, freshness, or provenance.
- Never use red, gray, shaking, or failure-shaped motion.
- Every animation has an equivalent instant state under Reduce Motion.
- Motion must remain legible on a phone and on a low-frame-rate projector.

## Button interaction

Every actionable control has five states:

| State | Visual response | Timing | Feedback |
|---|---|---:|---|
| Default | Normal fill, keyline, and elevation | — | — |
| Pressed | Scale to 97%; shadow compresses; fill deepens | 100 ms | Light haptic |
| Released | Return to 100% with a soft spring | 180 ms | — |
| Focused | 3 px sky-blue outer ring with 3 px offset | 120 ms | Screen-reader label |
| Unavailable | Pale-lavender fill and deep-indigo label | — | Tapping explains what is needed |

The marigold Scan control uses a medium haptic and briefly contracts its camera-aperture symbol. Other buttons use a light haptic. Unavailable controls never become gray.

## Screen transitions

### Hierarchical navigation

Opening a business, receipt, settings screen, or owner tool:

- Current screen moves 12 px left and fades to 88% opacity.
- Destination enters from 24 px right.
- Duration: 260 ms.
- Easing: `cubic-bezier(.2,.75,.25,1)`.
- Back navigation reverses the exact movement.

### Peer navigation

Switching between Map, Scan, and Profile:

- Content crossfades and settles upward by 8 px.
- Duration: 180 ms.
- Bottom-navigation selection indicator moves beneath the destination.
- No lateral slide because these destinations are peers.

### Bottom sheets

- Sheets follow the drag gesture one-to-one.
- Stops: 18% peek, 54% half, and 92% full height.
- Release velocity influences the destination stop.
- Snap duration: 320 ms with `cubic-bezier(.22,.9,.28,1.08)`.
- Opening from a selected entrance visually originates near that pin.
- The map dims with a 7% deep-indigo veil only at full height.

## Map and pin interaction

Trust tier and contextual prominence are independent systems.

### Fixed trust encoding

| Tier | Color | Shape and symbol | Ring |
|---|---|---|---|
| Estimated | Sky blue | Hollow dashed pin with italic `i` | 0 of 3 |
| Scanned on-site | Marigold | Solid pin with person | 2 of 3 |
| Owner-confirmed | Violet | Solid pin with storefront and outlined check | 3 of 3 |

### Contextual pin hierarchy

| Context | Estimated | Scanned on-site | Owner-confirmed |
|---|---:|---:|---:|
| Neighborhood overview | 32 px | 36 px | 40 px |
| Street/default map | 40 px | 44 px | 48 px |
| Selected | 52 px | 56 px | 60 px |
| Card or receipt | 24 px | 28 px | 32 px |

- Live scan drop: 64 px Scanned on-site pin.
- Mixed cluster: 48 px deep-indigo count marker with sky-blue, marigold, and violet composition arcs. A cluster never impersonates a trust tier.
- Render order: cluster 10, Estimated 20, Scanned on-site 30, Owner-confirmed 40, needs match 50, selected 60, live scan 70.
- Selection raises a pin 6 px, scales it approximately 12%, and adds a white keyline. It does not change the pin color.
- Match halo is external: solid for good match, dashed for partial, dotted for unknown.
- Freshness adds a muted-amber clock marker. It does not recolor the pin.
- Texas state provenance appears in the receipt or listing only, never on the map pin.

### Map camera

- Recenter and business selection: 450 ms geographic ease.
- Preserve the selected pin's screen position as the sheet opens.
- Filter changes crossfade affected pins over 180 ms.
- Newly relevant pins rise 4 px while their match halos draw.
- Overlapping unselected pins cluster before they become visually illegible.

## Live scan sequence

Total target duration: approximately 7.6 seconds and never longer than 8 seconds.

1. **Capture, 0–100 ms:** white shutter wash, medium haptic, and frozen camera frame.
2. **Frame confirmation, 100–380 ms:** doorway guide fades; photo contracts 3% into a rounded card.
3. **Processing, 380–7,000 ms:** progress ring advances while real checklist events appear:
   - Doorway framed
   - Entry path visible
   - Entrance features checked
   - Photo quality checked
4. A single soft violet highlight crosses the photo. Do not loop it and do not add decorative AI sparkles.
5. **Completion, 7,000–7,180 ms:** progress ring closes and the outlined check draws.
6. **Features, 7,120–7,360 ms:** visually confirmed chips enter with 60 ms staggering.
7. **Map return, 7,360–7,600 ms:** the photo card contracts toward its map location.
8. **Pin drop, 620 ms:** the Scanned on-site pin falls, squashes once, rebounds once, and settles with one sky-blue ripple.

Checklist items must correspond to completed processing steps; do not show fake progress labels.

## Receipts and feature chips

- Tapping a chip keeps the chip anchored while its receipt expands beneath it.
- Receipt height animates over 240 ms without moving the selected chip offscreen.
- Independent provenance lines appear together, not one at a time.
- Confidence dots fill from left to right, 70 ms apart.
- “Suggest a correction” remains visible at the end of every receipt.
- Unknown features use a neutral invitation: “Not yet seen — be the first to scan.”

## Feedback and system states

- Outlined checks draw over 180 ms.
- Toasts rise 12 px above bottom navigation over 220 ms, remain for 3–4 seconds, and can be swiped away.
- Offline scans fold into a “Saved for later” card; they do not shake or display a negative grade.
- A stale claim gains a muted-amber clock rotation of 20 degrees and returns to rest. Copy describes time, not the place.
- Correction completion reads “Suggestion sent” and displays a compact receipt animation.
- Permission denial keeps the user on a useful screen with “Open settings” and “Keep exploring.”

## Reduce Motion

When `prefers-reduced-motion: reduce` is active:

- Screen transitions become instant crossfades no longer than 80 ms.
- Sheets appear at their destination stop without spring movement.
- Processing retains the checklist and textual progress but removes sweeps, scaling, and rotation.
- The completed pin appears immediately with no bounce or ripple.
- Checks and confidence dots appear in their final states.
- Haptics remain available unless disabled by the operating system.

## Accessibility implementation

- Minimum touch target: 48 × 48 px.
- Keyboard focus is always visible and must not rely on motion.
- Announce processing changes through a polite live region; announce completion once.
- Do not announce decorative animation.
- Preserve focus when sheets change height and return focus to the opening control when they close.
- A screen transition never delays navigation or input availability.

