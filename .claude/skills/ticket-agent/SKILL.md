---
name: ticket-agent
description: Product-owner agent — turns spec documents into a strictly-formatted ticket backlog, extracting a numbered requirement register, decomposing it into single-domain tickets with testable acceptance criteria and a dependency graph, then proving coverage in both directions. Writes ticket files; does not write application code. Use when a spec or set of requirements needs to become tracked work.
---

# /ticket-agent

Runs the vendored ticket agent in this repository. It reads spec documents and emits ticket files
with a `BACKLOG.md` and a `CONVENTIONS.md`, optionally pushing them to a tracker.

## When to use it

When a body of requirements needs to become tracked work. It is built to generate a **backlog**,
so it earns its cost on a spec of real size. For one or two tickets against an established
backlog, writing them by hand is faster and matches the house format more reliably.

## Running it

```
python3 .claude/skills/ticket-agent/agent.py <spec-dir> \
  --yes --system github --target codeoritdidnthappen/frontdoor \
  --testing dod --no-push -o <output-dir-outside-the-repo>
```

- **Point it at a scoped spec, not at `docs/`.** This repository's `docs/` holds the whole-project
  proposal; running against it regenerates the entire backlog.
- **`-o` must point outside the repository.** The agent writes `BACKLOG.md`, `CONVENTIONS.md` and
  one file per ticket; none of that belongs in git, and a run must leave `git status --porcelain`
  empty.
- **Prefer `--no-push` and file the tickets yourself.** The agent may emit an epic or extra
  tickets in its own format; reviewing before anything reaches a tracker with a hundred live
  issues is cheaper than unpicking it afterwards.
- Do not run it interactively — a non-TTY session falls back to assume mode. Conduct any
  interview in chat and pass the answers as a file alongside the spec.
- A full run takes 15–30+ minutes. Run it in the background and poll.

Exit codes: `0` backlog complete, `2` incomplete.

## This repository's conventions

The agent does not know these. State them in the spec or the interview answers, and check the
output against them before filing.

- **Tracker:** GitHub Issues. **Target:** `codeoritdidnthappen/frontdoor`.
- **Ids:** `TICK-NNN`, unique across the backlog. Check the highest in use before allocating.
- **Body sections, in order:** `## Context`, `## Acceptance Criteria (Definition of Done)`,
  `## Out of Scope`. A `## Testing` section is included only where there is something to test.
- **Trailer block**, after a `---` rule:

  ```
  **TICK-NNN** · `type` · priority **P0** · estimate `S`
  Epic: EPIC-NN (#n)
  Implements: `D-0NN`
  Depends on: TICK-NNN (#n)
  ```

- **Assignment footer** — the current one:

  > _Assigned. Ownership follows the work division in TEAM.md §3 (TICK-003, #15), which supersedes
  > the self-assign-and-rotate convention from O-1. Reassignment is fine — change the assignee
  > rather than clearing it, so every ticket always names who is carrying it._

  The superseded **"Unassigned by design … (O-1)"** footer must not be reproduced. It was removed
  from 90 tickets by D-027, and any tool still emitting it will file issues whose footer
  contradicts their own assignee.
- **Labels:** one `type:*`, one `area:*`, one `priority:P0`–`P3`, plus `qa` and
  `pre-registration` where they apply.
- **Ownership:** tickets are assigned, not self-assigned (D-027). The work division is TEAM.md §3.

Filing to GitHub: strip the YAML frontmatter — the issue body starts at `## Context` — then append
the trailer and footer.

## A caution from use

The agent has read files outside the repository and reported a stale artefact from an unrelated
directory as a live defect. Verify anything it claims about this repo's state against the repo.

## Requirements

`claude-agent-sdk` (declared in `pyproject.toml` under the `agents` extra) and an
`ANTHROPIC_API_KEY` in the environment. Install with `pip install -e ".[agents]"`.
