# qa-agent

Agent #4 in the furtwangler series: an independent **QA engineer agent** that
tests the app built by [build-agent](../build-agent/) — or any app, or any
single part of one — on any technology stack, using whatever testing method
fits each surface.

The core stance: **the builder's passing tests prove the code agrees with
itself; QA proves it agrees with the requirements.** qa-agent reads the specs
(PRD requirements, USERS personas, ticket acceptance criteria), surveys the
app, then designs and executes a test matrix of *requirement × actor ×
method* — and every finding must cite captured evidence.

## Project scheduling policy

For the current frontdoor backlog, `/qa` and `/qa-agent` are deferred until all
currently scoped tickets are complete. Each ticket is locally tested, passed
through `/code-review`, fixed until no confirmed bugs remain, pushed through a
pull request, and merged immediately. Independent QA then runs across the
completed backlog; it is not a per-ticket pre-merge gate during this phase.

## Methods are chosen per surface, not fixed

| Surface | How qa-agent tests it |
|---|---|
| Web UI | Playwright scripts, headless, as each persona; screenshots as evidence |
| HTTP API | curl / small scripts, as each API actor incl. wrong-actor permission probes |
| CLI | runs the binary as a user would, incl. bad input and exit codes |
| Library | targeted scripts against the public interface |
| Integrations | your connected MCP tools when available (it loads your Claude Code settings), else mocks — and reports the gap |

Subagents do the surface work: `codebase-scout` (stack survey), `api-tester`,
`browser-tester`. The main session designs the matrix, orchestrates,
adjudicates findings, and writes the report.

## Setup

```bash
pip install claude-agent-sdk   # uses your Claude Code login, or ANTHROPIC_API_KEY
```

The agent installs per-project needs itself (deps, Playwright + Chromium)
inside the project's own tooling. It never modifies the app repo, never
touches production systems, and kills every process it starts.

## Usage — human (interactive)

```bash
qa-agent -r ./app -d ./docs -t ./tickets
```

You'll be asked: **what to test** (default: whole app; or "auth flows",
"the /routes API", "TICK-013 only") and **depth** (smoke / standard /
thorough). In interview mode it shows you the test plan before executing and
asks for anything it needs (credentials, URLs, environment quirks).

## Usage — another agent / script (headless)

```bash
qa-agent -r ./app -d ./docs -t ./tickets --yes
qa-agent -r ./app --scope "checkout flow" --depth thorough --yes
qa-agent -r ./app --yes --file-bugs ./tickets     # close the pipeline loop
```

Exit codes: `0` = PASS (nothing critical/major) · `3` = FAIL (findings
filed) · `2` = QA run incomplete · `130` = abort. The verdict is parsed from
the report on disk, not taken from the model's chat output.

## Output

```
qa/
├── QA_REPORT.md        # verdict, coverage matrix (incl. NOT TESTED gaps), findings
├── evidence/           # curl transcripts, screenshots, app logs, failing inputs
└── bugs/
    ├── TICK-B01-auth-bypass-on-admin-route.md
    └── TICK-B02-...
```

Bug tickets are **build-agent-compatible** (frontmatter, acceptance criteria,
repro steps, severity). With `--file-bugs ./tickets` they're copied into the
backlog, which completes the loop:

```bash
spec-agent ./notes --yes -o ./docs        # notes  -> specs
ticket-agent ./docs --yes -o ./tickets    # specs  -> backlog
build-agent -t ./tickets -d ./docs -r ./app --yes -p 4   # backlog -> app
qa-agent -r ./app -d ./docs -t ./tickets --yes --file-bugs ./tickets  # app -> bugs
build-agent -t ./tickets -d ./docs -r ./app --yes        # fix the bugs
# ...repeat qa-agent until exit code 0
```

That last cycle — build, test, file bugs, fix, re-test — is the whole point
of the series: a closed loop that converges on working software with a human
reviewing reports rather than driving every step.
