# CLAUDE.md

## 1. Think Before Coding

**Ask. Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.
- If there's a better approach, especially with long term benefits, propose it, even if it wasn't asked for.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting - don't touch it at all.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. Git Workflow

**Never work directly on `main`. Every change uses an appropriately named branch and a pull
request. When a ticket is complete, review it, fix every bug, and merge it immediately.**

1. **Trace.** Start from an up-to-date `main` and a ticket. Create a short-lived branch whose prefix
   matches the work, such as `feat/`, `fix/`, `docs/`, or `chore/`.
2. **Code.** Keep commits small and scoped to the ticket. Each commit message says what
   changed and why, and references the ticket. Never credit an AI tool anywhere — no
   `Co-Authored-By` trailers, "generated with" notes, or any other credit for Claude, Codex,
   Cursor, or any other AI assistant, in the commit message or anywhere else. Crediting a
   human teammate with a `Co-Authored-By` trailer is fine (clarified 2026-09-02; this was
   always the rule's intent).
3. **Test.** Before opening or updating a pull request, run the project's tests and checks locally.
   New behavior gets new tests. Never merge a state you haven't seen pass (the Windows-only
   shell-exec cases in test_ios_no_arkit.py are a known local exception; CI runs them).
4. **Review.** When the ticket's work is complete, run `/code-review`. Fix every confirmed bug on
   the same branch and repeat review as needed until no bugs remain. Do not run `/qa` or
   `/qa-agent` as a per-ticket pre-merge gate while the current ticket backlog is in progress;
   independent QA begins after all currently scoped tickets are complete.
5. **Land the PR.** Update the branch from `main`, resolve conflicts, and rerun the suite (and
   `/code-review` if conflict resolution changed the work). Then push the branch, open its pull
   request, verify CI passes, and merge it immediately. Changes discovered after merge start from
   a ticket and land through a new pull request. Automated agents are authorized and expected to
   perform this merge themselves once review and CI pass; do not leave a completed pull request
   open for a separate human merge.
6. **Land the whole ticket, or split it.** Don't land work that leaves its ticket
   incomplete. The moment an acceptance criterion turns out to need something the change
   cannot supply — hardware, a venue, another person, or work that is deliberately paused —
   **split that criterion into its own ticket and say what it is waiting on.** Then the
   original closes honestly.

   The failure this prevents is not a wrong ticket state, it is a **silent** one: a ticket
   left open with a criterion nobody can ever tick stops meaning "in progress" and starts
   meaning nothing at all. #50 could not close because one criterion needed James's iPhone on
   cellular; #55 could not close because two needed arms that are deprioritised. Both had
   landed, working, verified code sitting behind a checkbox.

   This is not a licence to file tickets instead of doing work — that rule stands. It
   applies only where the remaining criterion **cannot be done by whoever is holding the
   ticket**, and it needs a named owner.
7. **Never put a ticket number after a closing keyword — even to negate it.** GitHub closes
   an issue on `close/closes/fixes/resolves #N` in a commit message or PR body, and it does
   not read negation: the sentence *"Why this does not close #55"* closed #55. Write
   "#55 stays open", "does not complete #55", or `refs #55`.
8. **Say the ticket state on the ticket.** A PR body is read once, at merge, and never
   again; the issue is what a teammate finds later. When work lands without completing its
   ticket, post the criterion-by-criterion state as a comment on the **issue**.

If a change can't be traced to a ticket, ask before starting.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
