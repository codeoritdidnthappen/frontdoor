#!/usr/bin/env python3
"""ticket-agent — a product-owner agent that turns spec docs into tickets.

Agent #2 in the furtwangler series. Reads the structured docs produced by
spec-agent (PRD.md, ARCHITECTURE.md, USERS.md, README.md, ...) and generates a
complete, prioritized backlog — locally as markdown (always), and optionally
pushed to GitHub Issues, GitLab Issues, Linear, Jira, or any system you name.

Usable by a human (interactive) or by another agent (headless):

  python agent.py ./docs                                   # interactive
  python agent.py ./docs --yes                             # headless, local tickets
  python agent.py ./docs --yes --system github --target owner/repo
  python agent.py ./docs --yes --system jira --target PROJ --testing qa-tickets

Exit codes: 0 = backlog written, 2 = incomplete, 130 = user abort.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

HERE = Path(__file__).resolve().parent
SYSTEMS = ["local", "github", "gitlab", "linear", "jira"]
TESTING_POLICIES = {
    "dod": "tests are part of every ticket's definition of done (default best practice)",
    "qa-tickets": "each feature gets a linked, separately assignable QA ticket",
    "tdd": "acceptance criteria are written as failing-test specs; tests come first",
}
DONE_MARKER = "DONE"
MAX_NUDGES = 6


# --------------------------------------------------------------------------
# Input collection
# --------------------------------------------------------------------------

def collect_inputs(paths: list[str]) -> list[Path]:
    exts = {".md", ".txt", ".rst", ".markdown"}
    found: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if p.is_file():
            found.append(p)
        elif p.is_dir():
            found.extend(
                f for f in sorted(p.rglob("*"))
                if f.is_file() and f.suffix.lower() in exts and not f.name.startswith(".")
            )
        else:
            print(f"warning: input not found, skipping: {p}", file=sys.stderr)
    seen: set[Path] = set()
    return [f for f in found if not (f in seen or seen.add(f))]


# --------------------------------------------------------------------------
# Interactive prompts (skipped under --yes or when stdin is not a TTY)
# --------------------------------------------------------------------------

def choose_system() -> tuple[str, str]:
    print("\nWhere should tickets be created?")
    print("  1) local   — markdown files in the output directory (default)")
    print("  2) github  — GitHub Issues (needs `gh` logged in, and owner/repo)")
    print("  3) gitlab  — GitLab Issues (needs `glab` or GITLAB_TOKEN, and project path)")
    print("  4) linear  — Linear (needs LINEAR_API_KEY, and a team key)")
    print("  5) jira    — Jira (needs JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, and a project key)")
    print("  6) other   — name any system; the agent will research its API")
    choice = input("Choose [1-6] (default 1): ").strip().lower()
    mapping = {"": "local", "1": "local", "2": "github", "3": "gitlab",
               "4": "linear", "5": "jira", "6": "other"}
    system = mapping.get(choice, choice if choice else "local")
    if system == "local":
        return "local", ""
    if system == "other":
        system = input("Name the ticketing system: ").strip() or "local"
        if system == "local":
            return "local", ""
    prompts = {
        "github": "GitHub repo (owner/repo): ",
        "gitlab": "GitLab project path (group/project): ",
        "linear": "Linear team key (e.g. ENG): ",
        "jira": "Jira project key (e.g. PROJ): ",
    }
    target = input(prompts.get(system, f"Target for {system} (project/board/repo): ")).strip()
    return system, target


def choose_workflow() -> tuple[str, str]:
    print("\nHow should testing be handled for each ticket?")
    print("  1) dod        — tests are part of every ticket's definition of done (default)")
    print("  2) qa-tickets — each feature gets a linked QA/verification ticket")
    print("  3) tdd        — acceptance criteria written as failing-test specs first")
    ans = input("Choose [1/2/3] (default 1): ").strip()
    testing = {"": "dod", "1": "dod", "2": "qa-tickets", "3": "tdd"}.get(ans, "dod")
    notes = input(
        "Any other workflow rules? (branching, review, estimates, columns...)\n"
        "Press Enter for engineering best practices: "
    ).strip()
    return testing, notes


# --------------------------------------------------------------------------
# Agent construction
# --------------------------------------------------------------------------

def build_options(inputs: list[Path], output_dir: Path, system: str, target: str,
                  testing: str, notes: str, mode: str, push: bool,
                  model: str | None) -> ClaudeAgentOptions:
    workflow = (HERE / "TICKET_WORKFLOW.md").read_text(encoding="utf-8")
    system_prompt = (
        workflow
        .replace("{input_list}", "\n" + "\n".join(f"  - {p}" for p in inputs))
        .replace("{system}", system)
        .replace("{target}", target or "(none)")
        .replace("{output_dir}", str(output_dir))
        .replace("{testing_policy}", f"{testing} — {TESTING_POLICIES.get(testing, testing)}")
        .replace("{workflow_notes}", notes or "(none — use engineering best practices)")
        .replace("{mode}", mode)
        .replace("{push}", "yes" if push else "no (local files only this run)")
    )

    subagents = {
        "practice-researcher": AgentDefinition(
            description=(
                "Researches current industry best practices for ticket naming, "
                "sizing, acceptance criteria, and target-system conventions. "
                "Use in Phase 2, and for unfamiliar ticketing systems in Phase 6."
            ),
            prompt=(
                "You are a software-delivery practices researcher. Use web "
                "search to find CURRENT (last 1-2 years preferred) authoritative "
                "guidance on the topic you are given: official docs, respected "
                "engineering blogs, style guides. Distill to concrete, adoptable "
                "rules with source URLs. Flag where sources disagree and pick a "
                "recommendation. Return only the distilled findings."
            ),
            tools=["WebSearch", "WebFetch", "Read"],
        ),
        "ticket-reviewer": AgentDefinition(
            description=(
                "Reviews a generated ticket backlog for requirement coverage, "
                "traceability, dependency cycles, INVEST violations, and "
                "convention compliance. Use in Phase 7."
            ),
            prompt=(
                "You are a rigorous backlog reviewer. Read CONVENTIONS.md, "
                "BACKLOG.md and every ticket file in the directory you are "
                "given. Check: (1) every must/should requirement ID maps to at "
                "least one ticket; (2) traceability table matches ticket "
                "frontmatter; (3) depends_on graph has no cycles or dangling "
                "ids; (4) titles follow CONVENTIONS.md; (5) each ticket has "
                "testable acceptance criteria and a concrete Testing section; "
                "(6) no ticket implements nothing from the spec docs. Return a "
                "numbered list of concrete problems (file, issue), or 'NO ISSUES'."
            ),
            tools=["Read", "Glob", "Grep"],
        ),
    }

    allowed = ["Read", "Glob", "Grep", "Write", "Edit", "TodoWrite", "Task",
               "WebSearch", "WebFetch"]
    if push and system != "local":
        allowed.append("Bash")  # needed for gh/glab/curl in Phase 6 only

    return ClaudeAgentOptions(
        system_prompt=system_prompt,
        allowed_tools=allowed,
        permission_mode="acceptEdits",
        cwd=str(output_dir),
        agents=subagents,
        model=model,
        max_turns=200,
    )


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------

async def drain(client: ClaudeSDKClient, quiet: bool = False) -> str:
    last_text = ""
    async for msg in client.receive_response():
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    last_text = block.text
                    if not quiet:
                        print(f"\n{block.text}")
                elif isinstance(block, ToolUseBlock) and not quiet:
                    target = (block.input.get("file_path")
                              or block.input.get("path")
                              or block.input.get("command")
                              or block.input.get("query")
                              or block.input.get("description")
                              or "")
                    print(f"  [{block.name}] {str(target)[:100]}")
        elif isinstance(msg, ResultMessage):
            if msg.total_cost_usd and not quiet:
                print(f"\n-- turn done (${msg.total_cost_usd:.4f}) --")
    return last_text


async def run(inputs: list[Path], output_dir: Path, system: str, target: str,
              testing: str, notes: str, mode: str, push: bool,
              model: str | None, interactive: bool, quiet: bool) -> int:
    options = build_options(inputs, output_dir, system, target, testing, notes,
                            mode, push, model)

    kickoff = (
        "Begin the Ticket Agent Workflow now. Start with Phase 1 (Ingest) on "
        "the spec documents listed in your instructions."
        + ("" if mode == "interview" else
           " You are in assume mode: run every phase through Phase 8 without "
           "asking the user anything.")
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query(kickoff)
        text = await drain(client, quiet)

        while interactive and mode == "interview" and DONE_MARKER not in text.split():
            try:
                reply = input("\nyou> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nAborted.")
                return 130
            if not reply:
                continue
            if reply.lower() in {"quit", "exit"}:
                return 130
            await client.query(reply)
            text = await drain(client, quiet)

        # An agent that pauses mid-workflow gets nudged until it reports DONE.
        # Applies in assume mode too: without this the run ends after one turn,
        # usually before Phase 5 has written a single ticket.
        nudges = 0
        while DONE_MARKER not in text.split() and nudges < MAX_NUDGES:
            nudges += 1
            await client.query(
                "No human is available to answer questions. Switch to assume "
                "mode: record your assumptions and complete all phases now. "
                "Continue from where you stopped — do not summarize progress "
                "or wait for anything. Write the deliverables to disk, and "
                "reply DONE only once every file exists."
            )
            text = await drain(client, quiet)

    # Verify deliverables — files on disk, not the model's word, set the exit code.
    tickets = sorted(output_dir.glob("TICK-*.md"))
    required = {name: (output_dir / name).exists()
                for name in ("BACKLOG.md", "CONVENTIONS.md")}
    ok = all(required.values()) and len(tickets) > 0
    print("\n" + "=" * 60)
    for name, exists in required.items():
        print(f"  [{'ok ' if exists else 'MISSING'}] {output_dir / name}")
    print(f"  [{'ok ' if tickets else 'MISSING'}] {len(tickets)} ticket file(s) in {output_dir}")
    if push and system != "local":
        unpushed = [t.name for t in tickets
                    if "remote_url: null" in t.read_text(encoding="utf-8")]
        if unpushed:
            print(f"  [warn] {len(unpushed)} ticket(s) without remote_url "
                  f"(not pushed): {', '.join(unpushed[:5])}"
                  + (" ..." if len(unpushed) > 5 else ""))
    print("=" * 60)
    return 0 if ok else 2


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Product-owner agent: spec docs in, prioritized ticket backlog out.",
        epilog="Headless: agent.py ./docs --yes --system github --target owner/repo",
    )
    ap.add_argument("inputs", nargs="*", default=["./docs"],
                    help="Spec docs (files/dirs) from spec-agent (default: ./docs)")
    ap.add_argument("--output", "-o", default="./tickets",
                    help="Local ticket directory (default: ./tickets)")
    ap.add_argument("--system", default=None,
                    help=f"Ticketing system: {', '.join(SYSTEMS)}, or any name (default: local)")
    ap.add_argument("--target", default="",
                    help="System target: owner/repo, project path, team key, or project key")
    ap.add_argument("--testing", choices=list(TESTING_POLICIES), default=None,
                    help="Testing policy per ticket (default: dod)")
    ap.add_argument("--workflow-notes", default="",
                    help="Free-text workflow rules to override best-practice defaults")
    ap.add_argument("--mode", choices=["interview", "assume"], default=None,
                    help="interview = ask clarifying questions; assume = label assumptions")
    ap.add_argument("--no-push", action="store_true",
                    help="Generate local tickets only; skip pushing to the remote system")
    ap.add_argument("--yes", "-y", action="store_true",
                    help="No prompts; accept defaults (implies --mode assume unless set)")
    ap.add_argument("--model", default=None, help="Model override")
    ap.add_argument("--quiet", "-q", action="store_true",
                    help="Suppress streaming output; print only the final summary")
    args = ap.parse_args()

    inputs = collect_inputs(args.inputs)
    if not inputs:
        print("error: no readable spec documents found.", file=sys.stderr)
        sys.exit(2)

    interactive = sys.stdin.isatty() and not args.yes

    system, target = (args.system, args.target)
    if system is None:
        system, target = choose_system() if interactive else ("local", "")
    system = system.lower()
    if system != "local" and not target and interactive:
        target = input(f"Target for {system} (repo/project/team key): ").strip()

    testing, notes = args.testing, args.workflow_notes
    if testing is None:
        if interactive:
            testing, asked_notes = choose_workflow()
            notes = notes or asked_notes
        else:
            testing = "dod"

    mode = args.mode
    if mode is None:
        mode = "interview" if interactive else "assume"

    push = system != "local" and not args.no_push
    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nticket-agent: {len(inputs)} spec doc(s) -> {system}"
          + (f" ({target})" if target else "")
          + f" [testing: {testing}, {mode} mode"
          + (", push" if push else ", no push") + f"] -> {output_dir}")

    try:
        code = asyncio.run(run(inputs, output_dir, system, target, testing,
                               notes, mode, push, args.model, interactive,
                               args.quiet))
    except KeyboardInterrupt:
        code = 130
    sys.exit(code)


if __name__ == "__main__":
    main()
