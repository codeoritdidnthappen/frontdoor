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

**Every change starts with a ticket and lands on `main` directly. Fix forward.**
*(Amended 2026-09-01 by team decision: the PR-per-change workflow is retired — no new PRs
for review; fixes are made directly and pushed. The previous rule text is in git history.)*

1. **Trace.** Work begins from an up-to-date `main` and traces to a ticket. Short-lived
   branches are fine as a working convenience, but the destination is `main`, same day.
2. **Code.** Keep commits small and scoped to the ticket. Each commit message says what
   changed and why, and references the ticket. Never credit an AI tool anywhere — no
   `Co-Authored-By` trailers, "generated with" notes, or any other credit for Claude, Codex,
   Cursor, or any other AI assistant, in the commit message or anywhere else. Crediting a
   human teammate with a `Co-Authored-By` trailer is fine (clarified 2026-09-02; this was
   always the rule's intent).
3. **Test.** Before pushing to `main`, run the project's tests and checks locally. New
   behavior gets new tests. Never push a state you haven't seen pass (the Windows-only
   shell-exec cases in test_ios_no_arkit.py are a known local exception; CI runs them).
4. **Fix forward.** Review findings — your own or a teammate's — are fixed directly and
   pushed, not filed as new tickets or new PRs. Comment threads on old PRs/issues remain
   fine for discussion.
5. **Sync.** Pull before pushing; resolve conflicts locally, rerun the suite, then push.

If a change can't be traced to a ticket, ask before starting.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.