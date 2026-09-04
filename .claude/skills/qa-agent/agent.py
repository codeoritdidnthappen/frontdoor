#!/usr/bin/env python3
"""qa-agent — independent QA for apps built by build-agent (or any app).

Agent #4 in the furtwangler series. Reads the specs (what the app SHOULD do),
surveys the app (what was built), designs a test matrix of requirement x
actor x method — Playwright for browser users, curl/scripts for API clients,
subprocess for CLIs, connected MCP tools where relevant — executes it with
evidence capture, and files findings as build-agent-compatible bug tickets
plus a coverage-honest QA_REPORT.md.

  python agent.py -r ./app                                # interactive
  python agent.py -r ./app -d ./docs -t ./tickets --yes   # headless, full app
  python agent.py -r ./app --scope "auth flows only" --depth thorough --yes
  python agent.py -r ./app --yes --file-bugs ./tickets    # feed bugs back to the pipeline

Exit codes: 0 = PASS, 3 = FAIL (findings filed), 2 = QA run incomplete,
130 = user abort.
"""

from __future__ import annotations

import argparse
import asyncio
import re
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
DEPTHS = ["smoke", "standard", "thorough"]
DONE_MARKER = "VERDICT:"


def collect_docs(paths: list[str]) -> list[Path]:
    exts = {".md", ".txt", ".rst", ".markdown"}
    found: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if p.is_file():
            found.append(p)
        elif p.is_dir():
            found.extend(f for f in sorted(p.rglob("*"))
                         if f.is_file() and f.suffix.lower() in exts
                         and not f.name.startswith("."))
    seen: set[Path] = set()
    return [f for f in found if not (f in seen or seen.add(f))]


# --------------------------------------------------------------------------
# Interactive prompts
# --------------------------------------------------------------------------

def choose_scope() -> str:
    ans = input(
        "\nWhat should be tested? Press Enter for the whole app, or describe "
        "a part\n(e.g. 'auth flows', 'the /routes API', 'TICK-013 only'): "
    ).strip()
    return ans or "the whole application"


def choose_depth() -> str:
    print("\nTest depth?")
    print("  1) smoke     — critical paths only, fast")
    print("  2) standard  — all must-haves, happy + error + edge, every actor (default)")
    print("  3) thorough  — standard + boundaries, negative & basic security probes, NFR sanity")
    ans = input("Choose [1/2/3] (default 2): ").strip()
    return {"1": "smoke", "2": "standard", "3": "thorough"}.get(ans, "standard")


# --------------------------------------------------------------------------
# Agent construction
# --------------------------------------------------------------------------

def build_options(repo: Path, docs: list[Path], tickets_dir: Path | None,
                  scope: str, depth: str, output_dir: Path,
                  bugs_target: Path | None, mode: str,
                  model: str | None) -> ClaudeAgentOptions:
    sop = (HERE / "QA_WORKFLOW.md").read_text(encoding="utf-8")
    system_prompt = (
        sop
        .replace("{repo}", str(repo))
        .replace("{docs_list}", ("\n" + "\n".join(f"  - {p}" for p in docs))
                 if docs else "(none provided — derive expectations from the "
                 "app's own README and behavior, and say so in the report)")
        .replace("{tickets_dir}", str(tickets_dir) if tickets_dir else "(none provided)")
        .replace("{scope}", scope)
        .replace("{depth}", depth)
        .replace("{output_dir}", str(output_dir))
        .replace("{bugs_target}", str(bugs_target) if bugs_target
                 else "(none — bugs stay in the output directory)")
        .replace("{mode}", mode)
    )

    subagents = {
        "codebase-scout": AgentDefinition(
            description="Surveys the app repository: stack, entry points, how "
                        "to run it and its tests, config needs, external deps.",
            prompt=("You are a codebase scout. Explore the repository you are "
                    "pointed at (Read/Glob/Grep only) and return a concise "
                    "brief: language/framework/stack, entry points, how to "
                    "install deps, how to run the test suite, how to boot the "
                    "app (command, port, env vars), external services it "
                    "expects, and anything fragile. Return only the brief."),
            tools=["Read", "Glob", "Grep"],
        ),
        "api-tester": AgentDefinition(
            description="Tests HTTP APIs as a specified actor using curl or "
                        "small scripts; saves transcripts as evidence.",
            prompt=("You are an API test engineer. You are given a base URL, "
                    "an actor to impersonate (with auth details if any), test "
                    "cases to cover, and an evidence directory. Exercise each "
                    "case with curl (or a small script when curl is awkward): "
                    "happy paths, error paths, wrong-actor/permission probes. "
                    "Save full request/response transcripts to the evidence "
                    "directory. Return a structured result: case -> "
                    "PASS/FAIL, with expected vs actual and the evidence "
                    "filename for each FAIL. Never touch production systems."),
            tools=["Bash", "Read", "Write"],
        ),
        "browser-tester": AgentDefinition(
            description="Tests web UIs as a real user via Playwright: writes "
                        "and runs headless scripts, captures screenshots.",
            prompt=("You are a browser test engineer. You are given a URL, a "
                    "user persona (with credentials if any), flows to cover, "
                    "and an evidence directory. Write Playwright scripts "
                    "(Node or Python, whichever the project ecosystem "
                    "suggests; install Playwright + chromium if missing), run "
                    "them headless, and capture a screenshot at each key step "
                    "and on every failure into the evidence directory. Cover "
                    "the given flows plus obvious UI error states (bad input, "
                    "empty states). Return a structured result: flow -> "
                    "PASS/FAIL with expected vs actual and evidence "
                    "filenames. Always close browsers when done."),
            tools=["Bash", "Read", "Write", "Glob", "WebSearch", "WebFetch"],
        ),
    }

    return ClaudeAgentOptions(
        system_prompt=system_prompt,
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash",
                       "TodoWrite", "Task", "WebSearch", "WebFetch"],
        permission_mode="acceptEdits",
        cwd=str(output_dir),
        agents=subagents,
        # Load the user's Claude Code settings so their connected MCP servers
        # (test rails, browsers, DB tools, ...) are available to the session.
        setting_sources=["user", "project"],
        model=model,
        max_turns=400,
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
                    tgt = (block.input.get("file_path")
                           or block.input.get("command")
                           or block.input.get("query")
                           or block.input.get("description") or "")
                    print(f"  [{block.name}] {str(tgt)[:100]}")
        elif isinstance(msg, ResultMessage):
            if msg.total_cost_usd and not quiet:
                print(f"\n-- turn done (${msg.total_cost_usd:.4f}) --")
    return last_text


async def run(repo: Path, docs: list[Path], tickets_dir: Path | None,
              scope: str, depth: str, output_dir: Path,
              bugs_target: Path | None, mode: str, model: str | None,
              interactive: bool, quiet: bool) -> int:
    options = build_options(repo, docs, tickets_dir, scope, depth, output_dir,
                            bugs_target, mode, model)
    kickoff = (
        "Begin the QA Agent Workflow now. Start with Phase 1 (Orient)."
        + ("" if mode == "interview" else
           " You are in assume mode: run every phase through Phase 8 without "
           "asking the user anything.")
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query(kickoff)
        text = await drain(client, quiet)

        while interactive and mode == "interview" and DONE_MARKER not in text:
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

        if not interactive and mode == "interview" and DONE_MARKER not in text:
            await client.query(
                "No human is available. Switch to assume mode: record your "
                "assumptions and complete all phases now.")
            text = await drain(client, quiet)

    # Verify deliverables and parse the verdict from the report on disk.
    report = output_dir / "QA_REPORT.md"
    bugs = sorted((output_dir / "bugs").glob("TICK-B*.md"))
    print("\n" + "=" * 60)
    print(f"  [{'ok ' if report.exists() else 'MISSING'}] {report}")
    print(f"  [info] {len(bugs)} bug ticket(s) in {output_dir / 'bugs'}")
    verdict = None
    source = report.read_text(encoding="utf-8") if report.exists() else text
    # Accept "VERDICT: FAIL" as well as "## Verdict\n**FAIL (...)**" styles.
    m = (re.search(r"VERDICT:\s*(PASS|FAIL)", source, re.IGNORECASE)
         or re.search(r"\bverdict\b\W{0,80}?(PASS|FAIL)\b", source,
                      re.IGNORECASE | re.DOTALL))
    if m:
        verdict = m.group(1).upper()
        print(f"  [verdict] {verdict}")
    print("=" * 60)
    if not report.exists() or verdict is None:
        return 2
    return 0 if verdict == "PASS" else 3


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def allow_unencodable_output() -> None:
    """Keep a character the console cannot encode from ending the run.

    `drain` streams the model's own prose straight to stdout, and that prose routinely contains
    arrows and box-drawing characters. Where stdout is cp1252 -- a Windows console, or any
    redirect to a file or pipe on a Windows box -- one of them raised UnicodeEncodeError, which
    escaped `asyncio.run` and killed the process partway through a run, before any report was
    written. UTF-8 keeps the characters intact in a redirect; `errors="replace"` means anything
    still unencodable degrades to a placeholder instead of being fatal.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            # A stream that cannot be reconfigured (already detached, or replaced by a plain
            # object in an embedding host) is not worth failing the run over.
            pass


def main() -> None:
    allow_unencodable_output()
    ap = argparse.ArgumentParser(
        description="Independent QA agent: specs + app in, evidence-backed "
                    "report and bug tickets out.",
        epilog="Headless: agent.py -r ./app -d ./docs -t ./tickets --yes "
               "--depth standard --file-bugs ./tickets",
    )
    ap.add_argument("--repo", "-r", default="./app",
                    help="App repository to test (default: ./app)")
    ap.add_argument("--docs", "-d", default=None,
                    help="Spec docs dir/files from spec-agent (default: ./docs if present)")
    ap.add_argument("--tickets", "-t", default=None,
                    help="Ticket dir from ticket-agent, for acceptance criteria "
                         "(default: ./tickets if present)")
    ap.add_argument("--scope", default=None,
                    help="What to test (default: the whole application)")
    ap.add_argument("--depth", choices=DEPTHS, default=None,
                    help="smoke | standard | thorough (default: standard)")
    ap.add_argument("--output", "-o", default="./qa",
                    help="Output directory for report/evidence/bugs (default: ./qa)")
    ap.add_argument("--file-bugs", default=None, metavar="TICKETS_DIR",
                    help="Also copy bug tickets into this backlog dir so "
                         "build-agent can fix them")
    ap.add_argument("--mode", choices=["interview", "assume"], default=None,
                    help="interview = confirm plan, ask for creds/URLs; assume = autonomous")
    ap.add_argument("--yes", "-y", action="store_true",
                    help="No prompts; accept defaults (implies --mode assume unless set)")
    ap.add_argument("--model", default=None, help="Model override")
    ap.add_argument("--quiet", "-q", action="store_true",
                    help="Suppress streaming output; print only the final summary")
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not repo.exists():
        print(f"error: app repo not found: {repo}", file=sys.stderr)
        sys.exit(2)

    docs_arg = args.docs if args.docs else ("./docs" if Path("./docs").is_dir() else None)
    docs = collect_docs([docs_arg]) if docs_arg else []
    tickets_arg = args.tickets if args.tickets else (
        "./tickets" if Path("./tickets").is_dir() else None)
    tickets_dir = Path(tickets_arg).expanduser().resolve() if tickets_arg else None

    interactive = sys.stdin.isatty() and not args.yes
    scope = args.scope or (choose_scope() if interactive else "the whole application")
    depth = args.depth or (choose_depth() if interactive else "standard")
    mode = args.mode or ("interview" if interactive else "assume")

    output_dir = Path(args.output).expanduser().resolve()
    (output_dir / "evidence").mkdir(parents=True, exist_ok=True)
    (output_dir / "bugs").mkdir(parents=True, exist_ok=True)
    bugs_target = (Path(args.file_bugs).expanduser().resolve()
                   if args.file_bugs else None)

    print(f"\nqa-agent: testing {repo.name} [{scope}] at {depth} depth "
          f"({mode} mode) -> {output_dir}")

    try:
        code = asyncio.run(run(repo, docs, tickets_dir, scope, depth,
                               output_dir, bugs_target, mode, args.model,
                               interactive, args.quiet))
    except KeyboardInterrupt:
        code = 130
    sys.exit(code)


if __name__ == "__main__":
    main()
