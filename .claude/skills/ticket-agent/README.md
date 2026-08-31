# ticket-agent

Agent #2 in the furtwangler series: an autonomous **product-owner agent** that
reads the structured docs produced by [spec-agent](../spec-agent/) —
PRD.md, ARCHITECTURE.md, USERS.md, README.md and anything else in the docs
folder — and turns them into a complete, prioritized ticket backlog.

Tickets are always written **locally first** as reviewable markdown (source of
truth), then optionally pushed to **GitHub Issues, GitLab Issues, Linear,
Jira**, or any system you name (the agent researches its API).

## Architecture (same recipe as spec-agent)

| Part | Where | What it does |
|---|---|---|
| Workflow (SOP) | `TICKET_WORKFLOW.md` | Ingest specs → research current naming/workflow conventions (web search, cited in `CONVENTIONS.md`) → clarify → plan epics → write tickets → push → self-review → done. |
| Harness | `agent.py` | CLI that asks the setup questions (system? testing policy? workflow rules?), drives the SDK loop, and verifies deliverables on disk before exiting 0. |
| Model + tools | Claude Agent SDK | Read/Write/Search tools; Bash only when pushing to a remote system. Subagents: `practice-researcher` (best-practice lookup) and `ticket-reviewer` (coverage/traceability/INVEST audit). |

## Setup

```bash
pip install claude-agent-sdk    # uses your Claude Code login, or ANTHROPIC_API_KEY
```

Per-system credentials (only needed if you push):

| System | Needs |
|---|---|
| github | `gh` CLI logged in (`gh auth login`); target = `owner/repo` |
| gitlab | `glab` CLI logged in, or `GITLAB_TOKEN` (+ `GITLAB_HOST` if self-managed); target = `group/project` |
| linear | `LINEAR_API_KEY` env var; target = team key (e.g. `ENG`) |
| jira | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` env vars; target = project key |
| anything else | name it; the agent researches the API and confirms its plan |

## Usage — human (interactive)

```bash
python agent.py ./docs
```

You'll be asked: **which ticketing system** (default: local), **how testing
should be handled per ticket** (default: `dod` — tests are part of every
ticket's definition of done), and **any custom workflow rules** (default:
engineering best practices). Then it interviews you about milestones and
priorities before writing (type `quit` to abort).

## Usage — another agent / script (headless)

```bash
python agent.py ./docs --yes                                  # local tickets
python agent.py ./docs --yes --system github --target me/app  # push to GitHub
python agent.py ./docs --yes --system jira --target PROJ --testing qa-tickets
python agent.py ./docs --yes --system linear --target ENG --no-push  # draft only
```

Contract for callers: `--yes` (or non-TTY stdin) disables all prompts and
defaults to assume mode; exit `0` = backlog complete on disk, `2` =
incomplete, `130` = abort; writes only inside `--output` (default
`./tickets`) plus remote API calls when pushing. Unpushed tickets keep
`remote_url: null` in frontmatter, so a re-run or a human can recover.

## Output

```
tickets/
├── CONVENTIONS.md            # researched naming/workflow rules, with sources
├── BACKLOG.md                # epics, execution order, traceability, assumptions
├── TICK-001-project-scaffold.md
├── TICK-002-gymflow-oauth.md
└── ...
```

Each ticket: YAML frontmatter (id, title, type, epic, priority, estimate,
depends_on, labels, source requirement IDs, remote_url) + Context, Acceptance
Criteria, Testing, and Out of Scope sections. Every must/should requirement in
the PRD traces to at least one ticket.

## Pipeline (the series so far)

```bash
python agents/spec-agent/agent.py ./notes --yes -o ./docs \
  && python agents/ticket-agent/agent.py ./docs --yes -o ./tickets \
  && echo "backlog ready for a builder agent"
```
