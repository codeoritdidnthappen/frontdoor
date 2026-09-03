# Build-in-public tracker (TICK-116, #82)

Four floors, **graded per person**, by **2026-09-09** (PRD §11, `Capstone_Requirements.txt`):

| | Floor | Per |
|---|---|---|
| F1 | 150+ engagements on project posts | person |
| F2 | 25+ new followers | person |
| F3 | **5+ build-in-public posts** | person |
| F4 | 1+ repost or quote-post from **outside the team** | person |

Not project totals. Four people, four separate scorecards.

---

## The problem this tracker exists to surface, found on day one

**F3 cannot be met by the current plan, and the gap is 14 posts.**

PRD §11 plans six posts for the *project*, and #76–#81 give each one a single owner. F3 asks for
five posts from *each person*. So the plan tops out at two posts for the busiest person against a
floor of five, and it is arithmetically impossible for all four:

| Person | X handle | Posts owned in the plan | F3 floor | Short by |
|--------|----------|------------------------|----------|----------|
| David | @codehappened | 2 — #78, #79 | 5 | **3** |
| James | @JamesMerithew | 2 — #76, #77 | 5 | **3** |
| Emily | @EmilyLiangwx | 1 — #81 | 5 | **4** |
| Ruben | @rubanikov | 1 — #80 *(closed)* | 5 | **4** |
| | | **6 planned** | **20 needed** | **14** |

The ticket's own wording — "the six planned posts leave exactly one spare" — reads the six as one
person's set. Against per-person grading with one owner per post, they are not a spare; they are a
quarter of what is required.

**Five of the six are still unpublished with seven days left.** Only #80 is closed.

This is not a tracking gap to be filled in later. Either every person publishes ~5 posts of their
own, or the requirement is not met, and the remedy costs days — which is exactly why #82 asks for
tracking *from Aug 30* rather than a count on Demo Day.

**Owed to the team, not decided here:** whether the plan becomes "each person writes their own five"
or the floor is knowingly missed. Raise it before Sep 5, which is the date #82 sets for scheduling
extra posts.

---

## Scorecards

**No engagement or follower numbers have been recorded yet.** They are left as `not recorded`
rather than `0` on purpose: a zero is a measurement and would make the Sep 8 evidence wrong. The
first person to open an account fills the row in.

`start` is the follower count at the campaign's beginning; without it F2's *delta* cannot be
computed later, so it is the most urgent cell on this page — it becomes unrecoverable once the
number moves.

### David — @codehappened

| Floor | Status | Evidence |
|---|---|---|
| F1 engagements ≥150 | `not recorded` | — |
| F2 followers +25 | `not recorded` (start: `not recorded`) | — |
| F3 posts ≥5 | **1 published / 5** ⚠️ *(owns #78, #79)* | — |
| F4 outside repost | `not recorded` | — |

| # | Post | Ticket | URL | Published | Engagements |
|---|------|--------|-----|-----------|-------------|
| 3 | first honest error number | #78 | — | not yet | — |
| 4 | what pre-registration bought | #79 | — | not yet | — |

### James — @JamesMerithew

| Floor | Status | Evidence |
|---|---|---|
| F1 engagements ≥150 | `not recorded` | — |
| F2 followers +25 | `not recorded` (start: `not recorded`) | — |
| F3 posts ≥5 | **0 published / 5** ⚠️ *(owns #76, #77)* | — |
| F4 outside repost | `not recorded` | — |

| # | Post | Ticket | URL | Published | Engagements |
|---|------|--------|-----|-----------|-------------|
| 1 | the problem in one image | #76 | — | not yet | — |
| 2 | dataset build | #77 | — | not yet | — |

### Emily — @EmilyLiangwx

| Floor | Status | Evidence |
|---|---|---|
| F1 engagements ≥150 | `not recorded` | — |
| F2 followers +25 | `not recorded` (start: `not recorded`) | — |
| F3 posts ≥5 | **0 published / 5** ⚠️ *(owns #81)* | — |
| F4 outside repost | `not recorded` | — |

| # | Post | Ticket | URL | Published | Engagements |
|---|------|--------|-----|-----------|-------------|
| 6 | Demo Day measurement clip | #81 | — | not yet — needs Demo Day | — |

**#81 cannot be published before Sep 9**, so Emily's only planned post lands on or after the
deadline. Her F3 count from the plan is effectively zero.

### Ruben — @rubanikov

| Floor | Status | Evidence |
|---|---|---|
| F1 engagements ≥150 | `not recorded` | — |
| F2 followers +25 | `not recorded` (start: `not recorded`) | — |
| F3 posts ≥5 | **1 published / 5** ⚠️ *(owns #80, closed)* | URL not recorded |
| F4 outside repost | `not recorded` | — |

| # | Post | Ticket | URL | Published | Engagements |
|---|------|--------|-----|-----------|-------------|
| 5 | LiDAR vs a single photo | #80 | — | ticket closed — URL needed | — |

---

## F4 is the floor most likely to be missed

It depends on someone outside the team choosing to repost, so it cannot be produced on demand on
Sep 8. PRD §11 names the realistic audiences: the accessibility and civic-tech communities, and the
Project Sidewalk / Makeability Lab research line as a reasonable tag.

Tracked per person, with a link, because one outside repost of one person's post satisfies that
person's floor and nobody else's.

## Updating this file

- **Every two days**, per #82. The cadence was meant to start 2026-08-30; this tracker was created
  2026-09-02, so the first three checkpoints do not exist and cannot be reconstructed — engagement
  counts are not retroactive.
- **2026-09-08**: screenshot every account's numbers as evidence and put them in the Demo Day deck
  (#73). Screenshots, not this file — self-reported numbers are the claim that falls apart in Q&A.
- **Before Demo Day**: a second person checks these numbers against the live accounts. #82 requires
  the cross-check; an unverified tracker is worth less than no tracker, because it invites reliance.

## Out of scope

Buying engagement, follow-for-follow, or any inorganic growth. Platforms other than X. Aggregating
the team into one number — the requirement is graded per person.
