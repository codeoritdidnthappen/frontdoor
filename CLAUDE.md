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

**Every change starts with a ticket and ends at a pull request. A human takes it from there.**

1. **Branch.** Work begins from an up-to-date `main`. Create one branch per ticket, named so
   the ticket is identifiable from the branch name. Never commit directly to `main`.
2. **Code.** Keep commits small and scoped to the ticket. Each commit message says what
   changed and why, and references the ticket. Attribute every commit to the human author
   alone — no `Co-Authored-By` trailers, no "generated with" notes, and no other credit for
   Claude, Codex, or any other AI assistant, in the commit message or the PR description.
3. **Test.** Before pushing, run the project's tests and checks locally. New behavior gets new
   tests. Never push a branch you haven't seen pass.
4. **Sync.** Bring the branch up to date with `main` before opening the PR, and resolve
   conflicts on the branch — not in the review.
5. **Pull request.** Push the branch and open a PR that links the ticket and states what
   changed, why, and how it was verified.
6. **Stop.** Review, approval, and merge are human decisions. Do not self-approve, merge, or
   delete branches. Report the PR link and wait.

If a change can't be traced to a ticket, ask before starting.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.