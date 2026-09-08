# EntryMap — incentives audit

*What happens when the people using this product benefit from misrepresenting it.*

Read-only pass over the product canon (`product-interaction-design.md`), the reference spec
(`ui-reference-spec.md`), `visual-language.md` §13/§15, and the shipped implementation in
`C:\dev\frontdoor` — `src/frontdoor/scan_records.py`, `src/frontdoor/map_states.py`,
`src/frontdoor/claims.py`, `src/frontdoor_server/scan_view.py`,
`src/frontdoor_server/claim_view.py`, `src/frontdoor_server/map_view.py`,
`src/frontdoor_server/map.html`, and the tests that pin each rule.

Every previous round asked whether EntryMap is usable and honest. Both answers are yes, and both
are answers about a cooperative user. This is the adversarial pass: the same rules, read by
someone who profits from a wrong answer.

---

## Summary verdict

The honesty rules are real. They are enforced in Python, not asserted in comments, and the tests
pin them (`test_merge_never_downgrades_state_or_any_observation`,
`test_adversarial_verdicts_never_become_visible_observations`). Nothing below is a claim that the
never-negative model is fake.

The problem is narrower and worse. **Every honesty rule in the system constrains the *content* of
a claim, and none of them constrains the *provenance* of one.** The merge cannot be made to say
something bad about a business. It can be made to say something good about a business by anyone
with an HTTP client, about any door, from any photograph, permanently. The rules were designed
against a hostile *dataset* and deployed against a cooperative *network*, and the network is the
part that has people in it.

Three specific consequences, in order of how much damage they do:

1. The Owner-confirmed tier is currently reachable **without authenticating as the owner**.
2. Nothing in the system binds a photograph to the door it is published against.
3. A pin's tier is a function of **who looked**, not **what they found** — and it never goes back.

---

# Part A — Findings, ranked by damage if exploited

Ranked by blast radius, not by likelihood, per the brief. Each carries: the mechanism, whether it
is real in code or only in the design, what exploiting it costs, the cheapest fix, and which
settled honesty rule that fix strains.

---

## F1 — The owner attestation gate authenticates the *place*, not the *person*

**Damage: highest. The most authoritative tier in the product is anonymous.**

**Mechanism.** `scan_view.publish()` gates owner attestation like this
(`src/frontdoor_server/scan_view.py:237-246`):

```python
if attested:
    place_id = place_ref.get("place_id")
    if not has_approved_claim(
        os.environ.get(CLAIMS_ENV, DEFAULT_CLAIMS_PATH), place_id
    ):
        return _error("no approved claim", ..., status=422)
```

`has_approved_claim(path, place_id)` (`src/frontdoor/claims.py:265`) answers one question: *does
any approved claim exist for this place_id?* It does not take a token, a claim_id, or a
requester identity, because `/screen/publish` has no requester identity to take —
the endpoint is entirely unauthenticated, and the only caller field is `X-Frontdoor-Contributor`,
an optional self-declared opaque string (`scan_view.py:107`).

So: once **one** owner claim for a place is approved by a human, **any anonymous client on the
internet** may POST `place_id=<that place>&capture_kind=in_app&attested=1` with any photographs
and set `owner_confirmed: True` on that pin. The claim token that already exists
(`claims.py:238`, `secrets.token_urlsafe(32)`, and `token_matches` with `hmac.compare_digest`) is
the correct credential and is simply never consulted on this path. The test that supposedly pins
this gate — `tests/test_claims.py:380 test_in_app_attested_publish_requires_an_approved_claim` —
never sends a token either, which is why the hole passed review: the test asserts exactly the
property the code has.

There is a second, smaller edge on the same lines: the claim check runs *before* the engine call
(line 237 vs line 263), so a 422-vs-proceed comparison is a free oracle for enumerating which
places in the public dataset have approved claims.

**Real, or design-only?** Real in code today. The design is correct and the code does not
implement it: the spec's stated invariant is *"Login says who you are; it never says what you
own — the proof is always the confirmation step"* (`ui-reference-spec.md`, Account model). Here
neither half is checked.

**Cost to exploit.** One HTTP request. No account, no app, no key, no rate limit — there is no
rate limiting anywhere in the Flask app. Cost to the project if exploited: the Owner-confirmed
ring is the tier the whole trust ladder terminates in, and the product deliberately calls it
*attestation* rather than verification. An attestation from an unidentified party is not an
attestation at all; it is the exact thing §13 of `visual-language.md` refuses to build.

**Cheapest fix.** Require `claim_id` and `token` as form fields on any `attested=1` publish, and
gate on `token_matches(get_claim(path, claim_id), token)` **and** `record["status"] ==
"approved"` **and** `record["place_id"] == place_id`. Three conditions, all against functions
that already exist, roughly ten lines in `scan_view.py`. Add the negative test the current suite
lacks: an attested publish with no token, and with another place's token, must both 422.

**Which settled rule it strains.** None. This fix touches no public wording, no tier semantics,
never-downgrade, or Green-or-Gray. It is unambiguously a defect fix, and it is the cheapest
high-value change in this document.

---

## F2 — Nothing binds a photograph to the door it is published against

**Damage: very high. It defeats every downstream control at once.**

**Mechanism.** Three facts compose into a hole:

1. `frontdoor.faceblur.process_upload` re-encodes through OpenCV and drops the entire EXIF block,
   GPS included (`faceblur.py:22-30, 334-361`). This is deliberate and correct as privacy policy,
   and it happens at ingest, before anything else in the request sees the bytes.
2. The place a scan is published against is **client-supplied form data**:
   `_parse_place_ref(request.form)` reads `place_id`, or `lat`/`lng`/`name`
   (`scan_view.py:116-170`). It is validated for shape and bounds, never for correspondence with
   the photograph.
3. `capture_kind=in_app` and `attested=1` are likewise **plain form strings**
   (`scan_view.py:215-236`). The camera-roll ban — the spec's stated anti-staging control,
   *"Owner/verified-tier captures are in-app only with time+location attestation"* — is enforced
   by asking the client which one it is.

The server therefore has, and can have, **no evidence whatsoever** about where or when a
published photograph was taken. Photograph a compliant ramp at a hospital entrance and publish it
against a restaurant with three steps; nothing in the pipeline can object.

**Real, or design-only?** The hole is real. The control that would close it is design-only: the
spec's *"time+location attestation (anti-staging)"* has no implementation on the publish path.
Notably the mechanism already exists in the repo in a different context —
`src/frontdoor/capture_sidecar.schema.json` is a shutter-bound record written alongside an image
and hashed against its bytes, with `captured_at` fixed at the shutter press (D-018). It carries
no location field, and it is not wired to `/screen/publish` at all.

**Cost to exploit.** Zero marginal cost over an honest scan — this is not an attack so much as
the default state of the endpoint. Cost to the project: this is the finding that makes the other
findings unbounded. F1's fix authenticates the owner; it does not stop an authenticated owner
from photographing the neighbour's ramp. The never-downgrade rule then makes the result permanent
(F4). Every control in the system assumes the photograph is of the door named, and nothing
establishes that.

**Cheapest fix.** A shutter-bound capture attestation on the **attested path only**: the app
posts a small signed sidecar carrying capture timestamp and coarse device location; the server
checks it against the claimed place's coordinates within a generous radius and **discards it** —
it never enters the scan record, the object store, or `/map/data`. Community scans stay
unattested and unchanged. Second-cheapest, and worth doing regardless: bind `attested` to a
server-issued nonce from the workspace (`/claim/<id>/workspace` hands out a short-lived capture
token), which does not prove location but does prove the capture ran through the guided flow
rather than a curl command.

**Which settled rule it strains.** The privacy rule — *"faces are auto-blurred and GPS is
stripped at upload"* — and it is worth being exact about how. The settled guarantee is about what
is **retained and published**, not about what the request may momentarily contain: the module
docstring's own framing is that "the raw upload dies with the request." A location value that is
compared and dropped inside one request, never stored and never rendered, is inside that
guarantee's letter. It is nonetheless a real narrowing of it, and it should be written into the
privacy note in the scan flow rather than slipped in — the scan primer already says *"Only the
doorway is captured"*, and it would need a second line for the owner path. If that trade is
refused, the nonce fallback is available and strains nothing, at the cost of proving much less.

---

## F3 — A pin's tier reflects who looked, not what they found — permanently

**Damage: high. The map's strongest visual signal can be manufactured by photographing a barrier.**

**Mechanism.** `_upgrade_row` in `scan_records.py:338-340`:

```python
if state_for_row(row) != STATE_VERIFIED:
    row["status"] = "verified"
    row["source"] = OWNER_SCAN_SOURCE if is_owner_attested(scan) else SCAN_SOURCE
```

The promotion is unconditional on verdict content. `merge_scans` requires only a parseable
`created_at` and a `dict` of verdicts (`scan_records.py:364-366`). A scan whose four criteria all
come back `absent` — no ramp, no handrails, no accessible hardware, no signage — flips the row
from Estimated to the verified state, which `map.html:311` renders as the marigold **Scanned
on-site** tier. In `/map/data`, the same state carries `"label": "Verified Accessible"`
(`map_states.py:32-35`); the shipped map page happens not to render `pin.label`, but that string
is in a public JSON payload, and it is the canonical name of the state in the module that owns
Green-or-Gray.

To be fair to the build, the card is better than the pin: `map.html:611-618` distinguishes
`not_visible` (a labelled row, "Not visible in photos") from `not_assessed` (folded into the "Not
yet seen — be the first to scan" invitation). So a user who opens the sheet can tell the two
apart. A user scanning a map of pins cannot, and the pin is what a filter, a cluster, and a
glance operate on.

**Real, or design-only?** Real in code and pinned by
`tests/test_scan_records.py:251 test_a_scan_upgrades_a_neutral_pin_to_the_verified_scanned_state`.
The design does not clearly intend it: the product canon defines Scanned on-site as *"A community
member photographed the entrance in person"*, which is exactly what the code implements — but
the same document also says *"Pins only upgrade"* and treats the ladder as a strengthening of
evidence, and a rung that a barrier photograph climbs is not a strengthening of anything a user
cares about.

**Cost to exploit.** One photograph and one POST, and it never comes back down: the row can leave
the verified state through no code path (the docstring is explicit — "There is no code path that
writes any other status, removes a row, or lowers an observation").

**Cheapest fix.** Separate the two things the tier is currently conflating. Keep "someone looked"
as the tier — it is honest and it is what the label says — but stop letting the tier alone carry
prominence. Concretely: make pin size and z-order depend on *confirmed feature count*, not on
tier, so a Scanned-on-site pin with zero visible features renders no larger than an Estimated one.
`visual-language.md` §14 already frames size as answering "how much do we *know* about this
entrance?", and a scan that found nothing is not more knowledge about accessibility, only more
knowledge about the photograph.

**Which settled rule it strains.** §15's library principle — *"Trust tier and contextual
prominence are independent. Context may scale a pin but never changes its tier encoding."* Sizing
by confirmed-feature count is a *context* variable, not a tier re-encoding, so it survives the
letter of that rule; it does collide with §14's chosen mapping of size onto tier, and that
collision is already live and unresolved between §14 and §15. This is a design decision that
needs an owner ruling, not a fix an agent should make unilaterally.

---

## F4 — Never-downgrade makes a single false positive permanent, and there is no correction path in code

**Damage: high, and it compounds F2 and F3.**

**Mechanism.** Criterion merging is strictly monotone (`scan_records.py:327-330`):

```python
for key, entry in _scan_criteria(scan).items():
    if _rank(entry) > _rank(criteria.get(key)):
        criteria[key] = entry
```

Rank order is `not_assessed(0) < not_visible(1) < visible(2)`. Once any scan — model error,
adversarial, or of the wrong door — writes `visible` for `ramp_or_bevel`, **no subsequent
evidence of any kind can displace it.** Ten later scans that all disagree change nothing. The
`owner_confirmed` flag is the same: set at `scan_records.py:336-337`, cleared nowhere.

And the correction channel that the design leans on to absorb this does not exist as a system.
`map.html:637-646` renders "Suggest a correction" as a **`mailto:` link** to
`corrections@frontdoor.app`. There is no corrections endpoint, no store, no review queue. The
same is true of revocation: `set_dispute` (`claims.py:305`) writes a note onto the claim record,
and nothing anywhere reads `dispute` except `public_claim_view`, which returns it to the person
who wrote it. The spec's *"claims are revocable on dispute with no public trace"* is, in code, a
string field. Abandoning an approved claim makes `has_approved_claim` false for future publishes
but leaves every `owner_confirmed` scan record — and therefore the purple pin — in place forever.

**The authority inversion the brief asks about, answered precisely.** Yes, it is real, and it is
sharper than the framing assumed. It is *not* that an owner types "step-free: yes" and the system
believes them — the shipped owner path does not accept owner-authored verdicts at all; verdicts
on `/screen/publish` come from the model reading the photographs (`scan_view.py:404-411`). The
inversion is that the owner **chooses the photograph** and the never-downgrade rule then makes
the model's reading of that photograph permanent and irrefutable. The most authoritative tier is
the least verifiable, exactly as suspected, but the lever is the camera, not the form.

That distinction matters because of what the design plans next. `ui-reference-spec.md`'s owner
workspace specifies **Edit entrance** with per-feature `Yes / No / Not sure` dropdowns. That
surface is not implemented. If it ships and writes through the same monotone merge, it converts
self-attestation from a camera-aiming problem into a typing problem, and it is the single change
that would most damage the product's data. **Do not merge owner-typed feature values through
`_upgrade_row`.**

**Cost to exploit.** One POST for the write; unbounded for the victim, since the only remedy is a
human hand-editing `data/scans.jsonl` on the host.

**Cheapest fix.** Add a *contested* concept that lives entirely in internal state and confidence,
never in the public observation. When a new scan's entry ranks strictly lower than the stored
one, do not lower the stored one — record the disagreement, decrement the criterion's published
confidence toward one dot, and raise the place's re-check priority. The card already has the
neutral vocabulary for this: *"owner reports X; a scanner measured Y — help us re-check."* Also,
give the correction link a real endpoint before shipping; a `mailto:` is not a channel, it is a
place complaints go to die.

**Which settled rule it strains.** This is the one place where the obvious fix *looks* like it
breaks never-downgrade and does not. Never-downgrade governs the **published observation and
stamp state**. Confidence is a separate axis the spec already defines as *"strength and agreement
of evidence, not how accessible the entrance is"*, and item 9 of the reference spec already says
disagreements *"stay internal as scan priorities."* Lowering confidence on disagreement is
therefore inside canon and merely unbuilt. What would genuinely break never-downgrade — and
should not be done — is letting a later scan flip a published `visible` back to `not_visible`.

---

## F5 — Independence is unverifiable, so "sources agree" is forgeable

**Damage: moderate-high. It corrupts the one honest signal the product has left when tiers fail.**

**Mechanism.** `_attach_scan_provenance` (`map_view.py:129-152`) surfaces `scan_count`, which
`merge_scans` computes as `entry["scan_count"] += 1` per record — a count of **rows in a JSONL
file**, deduplicated by nothing. `contributor` is the optional self-declared header from F1. The
design renders this as *"Photographed Tuesday · 4 neighbors, 1 owner"* and defines confidence as
*"three (independent sources agree)"*. Four POSTs from one machine produce "4 neighbors."

`visual-language.md` §13 explicitly nominates confidence as the thing that does the work the tier
ladder cannot — *"Three sources agreeing is the strongest honest thing we can show."* That
sentence is only true if the three sources are three. Today the count is a count of requests.

**Real, or design-only?** The count is real. The account model that would make it meaningful
(Sign in with Apple / email magic link, *"'4 neighbors' = four distinct accounts"*) is
design-only — there is no account system in the server at all.

**Cost to exploit.** Trivial and unrated: there is no rate limiting in the Flask app, and
`/screen/publish` costs the attacker one model call's worth of the *project's* API budget per
request, which is its own denial-of-wallet observation.

**Cheapest fix.** Count distinct `contributor` values rather than records, and render that number
— it is still forgeable by rotating the header, but it stops being forgeable by accident and by
retry. Add a per-place, per-day publish ceiling. Neither is a substitute for the account model,
and the audit's honest recommendation is that **confidence should not be promoted to load-bearing
until accounts exist**, because §13 has already assigned it the weight that the tier ladder
refuses to carry.

**Which settled rule it strains.** None directly. It does strain the guest-first commitment if
over-corrected: requiring an account to scan would protect the count and shrink the contributor
pool that F7 shows is already the product's weakest link. Distinct-token counting is the version
that costs nothing.

---

## F6 — Domain-matched claims scale to a chain, and to a landlord

**Damage: moderate. Correct-by-design most of the time; wrong in exactly the cases that matter.**

**Mechanism.** `email_matches_listing` (`claims.py:109`) compares the claimant's email domain to
the **listing's** website host. For a fifty-location chain, all fifty listings carry the same
domain, so one mailbox at `chain.com` satisfies the domain check for every one of them. Each
claim is still a separate record and a separate human approval (`claim_view.claim_review`, gated
on `X-Frontdoor-Upload-Key`), so the *review* cost is O(n) — but the *verification* is O(1), and
review is a person clicking approve on a claim whose channel already says "verified."

The landlord case is the same mechanism through the phone channel. `listing_phone` reads the
listed number off the catalogue row; a landlord who controls a shared building reception line,
or who registered the domain a tenant trades under, passes. The spec is admirably honest about
this — *"channels verify control of the business's communication surface, not legal ownership —
acceptable because this tier is attestation, not independence"* — and that framing holds. What
it does not cover is that control of the communication surface is often held by a party with an
interest **adverse** to the tenant, and the product gives that party a permanent, uncontestable
write (F4) to the tenant's public accessibility record.

**Real, or design-only?** Real. The guardrail that matters *is* implemented and worth crediting:
`claim_view.claim_submit:97-102` refuses a claim carrying a `phone` field outright — the claimant
cannot supply the contact point, which is the proof-of-control invariant, correctly upheld.

**Cost to exploit.** One mailbox, or one phone line, plus the patience to pass manual review.

**Cheapest fix.** Rate-limit approvals per domain and per reviewer session, and surface the
count in the review UI ("this domain has 47 approved claims") so bulk claiming is a decision
rather than a side effect. Separately, make dispute do something: a dispute on an approved claim
should suspend `has_approved_claim` for that place pending review, which is a five-line change to
`has_approved_claim` and requires no public negative state at all — the pin simply stops being
eligible for *new* owner attestations.

**Which settled rule it strains.** Nothing, provided the suspension is invisible publicly, which
the spec already requires (*"revocable on dispute with no public trace"*).

---

## F7 — The tax-credit hook is currently framed right, and it is one screen away from being framed wrong

**Damage: moderate, and asymmetric — it is cheap to keep right and expensive to recover from.**

**Mechanism.** `INCENTIVES_TEXT` is a single string (`claims.py:34`): *"Accessibility fixes may
qualify for federal tax credits — ask your accountant."* In the server it is returned from
exactly two places: `public_claim_view` (a record the claimant already owns) and
`/claim/<id>/workspace` (`claim_view.py:181`), which is reachable only after approval. So in
code, **the tax credit is mentioned only to a party who has already proven control** — which is
the right place, and the tests even pin the disclaimer wording
(`tests/test_claims.py:269-271`, asserting "ask your accountant" and no "tax advice").

The design puts it earlier. `product-interaction-design.md` places it on the pre-claim Profile
invitation: *"Claim your door — get scanned, get seen. Accessibility fixes may qualify for
federal tax credits."*

**Which incentive does it create?** Three are available and the framing picks between them:

- **Incentive to claim** — good, and the point. Claiming is the funnel.
- **Incentive to improve** — the intended prize. Section 44 pays for a *fix*, so the credit is
  one of the few product mechanics that pays the owner for changing the physical world rather
  than the record of it. That is genuinely rare and worth protecting.
- **Incentive to misreport** — the failure mode, and it is *not* the one people expect. A tax
  credit rewards spending money on an entrance that was **not** accessible. Its natural pull is
  toward *understating* the before-state, not overstating the after-state. EntryMap has no
  before-state to understate and no public negative to hide behind, so the credit does not create
  a direct falsification incentive against the map.

The real risk is adjacency, not incentive: the credit line sitting on the same card as "get
scanned, get seen" invites the owner to read Owner-confirmed as the thing the credit is for. It
is not; the credit is for the ramp. As long as the copy pairs the credit with the **fix** and not
with the **badge**, the framing pushes toward improvement, which is the right one.

**Cheapest fix.** Keep the credit line attached to the unknown/missing-feature surface (*"a fix
here may qualify…"*) rather than to the claim CTA, and never place it in the same visual group as
the Owner-confirmed preview in the claim tracker. This is a copy-placement rule, not a code
change.

**Which settled rule it strains.** None. It reinforces the existing "features, not legal claims"
rule, and the "ask your accountant" disclaimer is already enforced by test.

---

## F8 — Step-free entry is not in the published criterion vocabulary

**Damage: moderate, and it re-scopes everything above.**

**Mechanism.** `map_states.CRITERIA` is exactly four keys: `ramp_or_bevel`, `handrails`,
`accessible_door_hardware`, `accessibility_signage`. **Step-free entry is not among them**, and
`checklist_for_row` iterates only that tuple, so a scan reporting step-free would be dropped from
the public checklist. Meanwhile the product canon lists "Step-free entry" first among feature
chips, `visual-language.md` §13 calls it *"the criterion people most need"*, and the filter sheet
leads with it.

**Real, or design-only?** The gap is real. §13 also documents the intended answer — on-site scans
and monocular depth (88.5% → 96.2% held out) — so this is a wiring gap, not an unsolved problem.

**Why it belongs in an incentives audit.** It changes what is being gamed. Today the four
gameable assertions are relatively low-stakes: signage and hardware are cheap to photograph
honestly and cheap to fix. The moment step-free enters the published vocabulary, it becomes the
single most valuable false claim in the product — the one that strands a wheelchair user at a
door — and it inherits **every** weakness above simultaneously: no photo-to-door binding (F2),
permanent on first `visible` (F4), settable by an unauthenticated attested publish (F1).

**Cheapest fix.** Land F1 and F4's contested-confidence mechanism **before** step-free is added
to `CRITERIA`, not after. Sequencing, not code.

**Which settled rule it strains.** None. Adding the criterion is required by canon; this is only
a claim about ordering.

---

# Part B — The two questions that are arguments, not defects

## B1. Green-or-Gray: absence of evidence and evidence of a barrier

The brief asks for both sides argued properly before a conclusion. Here they are, with what the
code actually does folded in, because the implementation is more nuanced than the rule's name
suggests.

**What is actually true in the build.** Green-or-Gray is a rule about the **stamp**, and the
stamp is binary — `state_for_row` is total and admits no third value, by construction and by
test. But the **card** is not binary: `map.html:611-627` renders `not_visible` as its own labelled
row ("Not visible in photos") and folds only `not_assessed` into the "Not yet seen — be the first
to scan" invitation. A user who opens the sheet **can** distinguish "we looked and saw no ramp"
from "nobody has looked." A user reading pins, clusters, or match halos cannot, because those are
computed from state and confirmed-feature counts, and both of those treat the two cases alike.

So the honest framing of the problem is not "the product cannot say it." It is: **the product
says it in the one place a person has to already be committed to reach, and stays silent in the
three places a person actually plans from.**

**The case for the rule.** It is not squeamishness; it is four separate arguments that each hold
independently.

- *Legal.* A public map that publishes "this business is not accessible" against a named, located
  business, derived from a model reading a photograph, is a defamation and ADA-adjacent exposure
  the project cannot carry. `map_states.py`'s own docstring names this: *"the legal and backlash
  shield for putting real businesses on a public map."*
- *Epistemic.* The system genuinely cannot distinguish "there is no ramp" from "the ramp is not
  in this frame." `_observation` collapses the model's `absent` and `not_visible` into one public
  word precisely because the model's confidence in that distinction does not survive a single
  photograph from an unknown angle. Publishing a negative would be publishing a claim the
  evidence does not support — which is the same honesty failure the audit is otherwise arguing
  for.
- *Incentive.* A public negative gives every business owner a reason to fight the map, and gives
  competitors a weapon. Under F1–F4 that weapon would be cheap, anonymous, and permanent. The
  never-negative rule is the single largest reason the adversarial findings above are *survivable*
  rather than catastrophic: an attacker who wants to hurt a business currently cannot, because the
  worst thing they can publish is a compliment.
- *Cultural.* The product's whole posture — invitation, never apology; no red; no failing state —
  is coherent, and it is the reason businesses might cooperate at all. A map that shames does not
  get claimed.

**The case against.** One argument, and it is heavier than any of the four.

- The user can be **physically stranded**. Every other party in this system loses something
  recoverable when the data is wrong: reputation, a customer, a tax deduction. The wheelchair
  user who travels to a door with three steps loses the trip, and depending on the city, the
  transport back. That asymmetry is not a tie-breaker, it is a different weight class. A rule
  whose costs fall on the party who cannot absorb them needs a better defence than "it is
  legally safer for us," and the legal argument is, stated plainly, a rule that protects the
  publisher at the expense of the person the publisher exists to serve.
- The rule also **fails silently in the direction of false comfort**. Grey reads as "unknown,"
  and unknown reads as "possible." Nothing in the interface tells a planning user that this
  particular grey is a grey somebody already investigated. That is not neutrality; it is a lossy
  encoding whose loss always falls the same way.

**Conclusion.** The trade is correct at the level of the **public stamp** and wrong at the level
of the **planning surface**. Keep the rule exactly as it is: no negative stamp, no red, no
failing state, no third value out of `state_for_row`. The four arguments for it hold and the
legal one is not optional.

But "never publish a negative" was never the same commitment as "never distinguish a *checked*
unknown from an *unchecked* one," and the build already draws that distinction on the card. The
fix is to carry the distinction the card already makes onto the surfaces people plan from, in
time-and-evidence language rather than verdict language, which the product's own vocabulary
already supports:

- **Halos.** Split Unknown into *checked-not-confirmed* (dotted) and *never-checked* (dotted,
  hollow, plus the existing "be the first to scan" invitation). Line style already carries state
  independent of colour, which is the accessibility rule, so this costs nothing in contrast terms.
- **Filters.** When a user filters for step-free, a place whose step-free criterion was assessed
  and not confirmed should be *ordered below* a place never assessed, and labelled "checked —
  not confirmed." That is a statement about the evidence, not about the business, and it is the
  same grammatical move the product already makes with freshness.
- **Never** as a red pin, a failing badge, a "not accessible" string, or a filter facet.

**Which settled rule this strains.** Not Green-or-Gray, which is about the stamp and stays
untouched. It does strain *"'not visible' never rendered as 'absent'"* — and it must not cross
that line: "checked — not confirmed" is a statement about the checking, and the moment the copy
drifts to "no ramp found" the rule is broken. It also strains the "no negative state anywhere,
ever" maximalist reading of the language rules. That tension is real and the owner should rule on
it explicitly, because a wheelchair user stranded by a grey pin is the product's worst outcome
and the current design has no mechanism that prevents it.

---

## B2. Community scanning is unpaid labour with no reward

**Who scans today?** Structurally, three groups, in descending size:

1. **Nobody.** This is the honest baseline answer and it should be the planning assumption.
2. **Disabled users who are already at the door.** They are the ones who know the answer, and
   they are the worst possible people to ask: they are the party the app exists to save a trip,
   and by the time they can scan, the trip is already spent. Asking them to scan is asking the
   injured party to do the survey.
3. **The project's own operators.** §13 records exactly this: *"11 of 64 places show as Scanned
   on-site while the operator photographed all 64."* The seeded coverage in this product came
   from the team, and that is not a community — it is a demo with a community-shaped interface.

**What do they get?** In the current build, nothing. Not points, not a profile count, not
acknowledgement — the design explicitly rejects streaks, guilt, and public leaderboards, and the
server does not even reliably attribute a scan to a person (F5). The only reward is the
provenance line "Scanned on-site," which names no one.

**What happens to coverage if the answer is nobody?** The Estimated tier becomes permanent, which
is the actual failure the product has already half-experienced. The estimate is designed to *want*
to be replaced — *"been here? Confirm in 30 seconds"* is called "the growth loop" in the reference
spec — and a growth loop with no contributor is just a disclaimer. Worse, evidence decay is
scheduled: structural criteria have a years-long half-life but tenancy-coupled criteria decay in
months and a turnover event demotes every imagery-derived observation at that address. **Coverage
does not plateau, it erodes**, and unpaid volunteers are the only thing in the design that
refills it.

**What would make it worth doing without corrupting the data?** The rule to apply is: *reward the
act, never the verdict, and never at a rate that scales.* Every points-and-badges system applied
to factual reporting fails the same way — it pays per unit of reported fact, so it manufactures
reported facts. Four options, in descending order of how well they survive that test:

- **Pay the operator, not the crowd.** The most honest answer, and the one the project has
  already run: contract walk-by video coverage of a block face (the "map your block" mode, 82%
  commit rate vs 20% for Street View). The contributor is paid for *coverage*, the verdicts come
  from the engine reading the frames, and *"Door inventory comes from the frames, never the
  walker's memory."* The incentive is to walk the whole block, which is exactly the behaviour
  wanted, and it cannot be gamed by claiming a feature because the walker never claims anything.
- **Reward being asked, not being right.** Re-check nudges directed at people who have already
  saved a place — "you saved this; it was last checked 11 months ago." The ask is targeted, the
  reward is that a place the person cares about stays current, and there is no per-scan currency
  to farm.
- **Route the ask to the party with the commercial interest.** The owner funnel is the only
  actor in the system with a standing, self-interested reason to maintain a record — and, per F7,
  a subsidised reason to improve the thing the record describes. That is a better engine than
  altruism and the product already has it; it is just gated behind a claim flow with no
  authentication (F1).
- **Reciprocity, carefully.** "Places you scanned have been viewed 340 times" is a real reward, is
  proportional to usefulness rather than volume, and is not a currency. It is also one design
  meeting away from becoming a leaderboard, which the canon rightly bans.

**What not to build:** per-scan points, contributor levels, badges, or streaks. Each of them pays
per assertion, and paying per assertion under a merge rule that can never lower an assertion
(F4) is the worst combination in this document.

---

# Part C — The adversarial cases, scored

| Case | Outcome today | Where |
|---|---|---|
| **Competitor scans a rival's entrance badly** | **Partly caught.** Cannot lower any observation or state — never-downgrade holds. **But** it can write `not_visible` onto criteria that were silent, permanently, *and* promote the pin to the Scanned tier so the place reads as examined-and-lacking. Unauthenticated, unrated, unattributable. | `scan_records.py:327-340`; F3, F4, F5 |
| **Landlord claims a tenant's door** | **Accepted** whenever the landlord controls the listed phone or the listing domain. The spec acknowledges this limit honestly; the code has no tenant-side notification, and dispute is a text field nothing reads. | `claims.py:109-124, 305-323`; F6 |
| **Chain claims fifty locations at once** | **Accepted, and cheap.** One mailbox at the chain domain satisfies the domain check for all fifty listings; per-claim human review is the only friction, and it sees a channel already marked verified. | `claims.py:109`; F6 |
| **Someone photographs a different door than the one they say** | **Wholly accepted.** No location, no time, no binding of any kind. GPS is destroyed at ingest before anything could check it, and the place reference is client-supplied form data. | `faceblur.py:334-361`, `scan_view.py:116-170`; F2 |
| **Anonymous party publishes an owner-attested scan for a claimed place** | **Accepted.** No token is checked; `has_approved_claim` asks about the place, not the requester. | `scan_view.py:237-246`; F1 |
| **Contributor inflates "neighbors" by publishing four times** | **Accepted.** `scan_count` counts records; no rate limit exists. | `map_view.py:129-152`; F5 |
| **Scan published against a place that does not exist** | **Accepted** — creates a new pin under a synthetic `scan:<id>` key with an attacker-supplied name and coordinates. Never-negative bounds the damage to a fabricated *positive*. | `scan_records.py:264-266` |
| **Claimant supplies their own contact point to receive the code** | **Caught.** Refused outright at submit; the contact is resolved from the listing, never from the claimant. This invariant is correctly implemented. | `claim_view.py:97-102`, `claims.py:195-223` |
| **Camera-roll photo used for owner tier** | **Caught in form, not in fact.** The 422 is real, but `capture_kind` is a client-declared string, so the check binds honest clients only. | `scan_view.py:224-236`; F2 |
| **Adversarial verdict strings crafted to publish a negative** | **Caught.** `_observation` is total and default-neutral; no input produces a third state or a negative claim. Pinned by test. | `map_states.py:88-95`; `test_adversarial_verdicts_never_become_visible_observations` |

---

# Part D — The three that would most change the product

**1. Authenticate the attestation (F1), then bind the photograph to the door (F2).**
These are one change with two halves, and until both land, "Owner-confirmed" names a property the
system does not have. The first half is ten lines against functions that already exist and strains
no settled rule; there is no argument for not doing it. The second half requires an owner ruling
on a narrow, stated narrowing of the privacy line — a location value compared and discarded inside
one request, never stored, never published — and the fallback (a workspace-issued capture nonce)
is available if that trade is refused. Everything else in this audit is downstream of these two.
An unauthenticated top tier is not a bug in the trust ladder; it is the absence of one.

**2. Give never-downgrade a companion: contested-not-lowered (F4).**
The rule that protects good data currently protects bad data identically and forever, and the
correction channel meant to absorb that is a `mailto:` link. The fix is already canon and merely
unbuilt — confidence is defined as *agreement between sources*, and §9 of the reference spec
already says disagreements *"stay internal as scan priorities."* Implement that: a disagreeing
scan never lowers the published observation, but it does decrement confidence, mark the criterion
contested, and raise re-check priority. This is the change that makes the product *correctable*,
which it presently is not, and it must land **before** step-free enters the published criterion
vocabulary (F8), because step-free is the claim that strands people.

**3. Carry the card's honesty onto the planning surface (B1).**
The build already distinguishes "checked, not confirmed" from "never checked" — on the card, one
tap past the point where a person has already committed to a place. Every surface people actually
plan from (pins, halos, filters, clusters) flattens the two. Keep Green-or-Gray exactly as it is;
it is doing real work and it is most of what makes the adversarial findings survivable. But split
Unknown into checked and unchecked in the halo and the filter ordering, in time-and-evidence
language, never verdict language. This is the only finding in the document whose cost is measured
in stranded people rather than corrupted records, and it is the one the honesty rules were not
written to cover — because they were written to protect the businesses on the map, and this is
the one place where that protection and the user's safety point in different directions.
