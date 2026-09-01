---
name: qa-agent
description: Independent QA agent — verifies a branch, PR or component against its ticket's acceptance criteria on any stack, as a real actor, and reports findings that reproduce and carry evidence. Writes nothing to the repo and commits nothing. Use before merging a pull request, or when a change needs verifying by something that did not write it.
---

# /qa-agent

Runs the vendored QA agent in this repository. It reads a ticket, exercises the code against that
ticket's acceptance criteria, and returns a verdict with reproducible findings.

It **writes nothing to the repository and commits nothing.** Its only output is a report directory.

## When to use it

Before merging a pull request, and any time a change needs verifying by something that did not
write it. Every `qa`-labelled ticket in this backlog exists because verification here is meant to
be independent — the author of a change does not verify it, and neither does the agent that wrote
it.

## Running it

```
python3 .claude/skills/qa-agent/agent.py \
  -r . -d . -t <tickets-dir> \
  --yes --depth standard -o <output-dir-outside-the-repo>
```

- `-r` / `-d` are the repository root; this project keeps `PRD.md` and `ARCHITECTURE.md` there.
- `-t` is a directory of ticket files. Export the relevant GitHub issues into it first:
  `gh issue view <n> --json number,title,body -q '"# \(.title)\n\n\(.body)"' > <dir>/TICK-nnn.md`
- **`-o` must point outside the repository.** The agent writes a report directory, `bugs/` and
  `evidence/`; none of that belongs in git, and acceptance criterion 7 of TICK-226 requires that a
  run leaves `git status --porcelain` empty.
- Do **not** run it interactively. A non-TTY session falls back to assume mode, which is what you
  want; `--yes` is required for a headless run.
- Standard depth takes 10–30 minutes. Run it in the background and poll.

Exit codes: `0` pass, `3` fail (findings reported), `2` incomplete.

## Give it what it cannot work out for itself

The single biggest lever on output quality is a briefing file. Write one and name it in `--scope`:

- **How to run the tests.** This project uses a `src/` layout, so a bare `pytest` fails at
  collection with `ModuleNotFoundError`. The package must be installed editable first
  (`pip install -e ".[dev]"`), and the venv path should be given explicitly.
- **The baseline**, so a pre-existing failure is not reported as a regression.
- **Known issues not to re-report**, so effort goes to new ground.
- **What the change actually protects.** For a pre-registration project the threat model is rarely
  a crash — it is a split that silently changes, a hash that is not really checked, a contract that
  cannot express an outcome.
- **What is out of scope**, including files that are duplicates of `main` because a branch was cut
  before its predecessor landed.

## After a run

Findings are reported, not filed. Raise the ones worth fixing as GitHub issues in the house ticket
format, then record coverage on the paired `qa` ticket — including, explicitly, which of its
acceptance criteria were **not** exercised. Most `qa` tickets here depend on several tickets, so a
single run rarely satisfies one, and a closed QA ticket must never imply verification that did not
happen.

## Requirements

`claude-agent-sdk` (declared in `pyproject.toml` under the `agents` extra) and an
`ANTHROPIC_API_KEY` in the environment. Install with `pip install -e ".[agents]"`.
