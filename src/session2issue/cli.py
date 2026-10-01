"""Console interface for Session2Issue."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import __version__
from .ai import summarize
from .redact import Redactor
from .report import build_draft
from .session import Session, SessionError, candidates, codex_home, discover_sessions, parse_session


def _sessions(limit: int = 20) -> list[Path]:
    paths = discover_sessions(limit)
    for index, path in enumerate(paths, start=1):
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            modified = "unknown time"
        try:
            label = path.relative_to(codex_home())
        except ValueError:
            label = path
        print(f"{index:>2}. {modified}  {label}")
    return paths


def _choose_path(ask: Callable[[str], str]) -> Path:
    paths = _sessions()
    if not paths:
        raise SessionError("No Codex sessions found; pass a JSONL file path explicitly")
    raw = ask("Choose a session number: ").strip()
    if not raw.isdecimal() or not 1 <= int(raw) <= len(paths):
        raise SessionError("Invalid session selection")
    return paths[int(raw) - 1]


def _choose_line(session: Session, ask: Callable[[str], str]) -> int:
    found = candidates(session)
    redactor = Redactor()
    if found:
        print("Possible failure events (choose a number or enter 'line N'):")
        for index, event in enumerate(found[:30], start=1):
            preview = " ".join(redactor.clean(event.text[:180]).split())
            print(f"{index:>2}. line {event.line}: {preview}")
        if len(found) > 30:
            print(f"{len(found) - 30} more candidates omitted; use 'line N' to select one.")
    else:
        print("No obvious error event found. Enter a JSONL line number to report.")
    raw = ask("Failure event: ").strip().lower()
    if raw.startswith("line ") and raw[5:].strip().isdecimal():
        return int(raw[5:].strip())
    if raw.isdecimal() and 1 <= int(raw) <= min(len(found), 30):
        return found[int(raw) - 1].line
    raise SessionError("Choose a candidate number or enter 'line N'")


def _draft(args: argparse.Namespace, ask: Callable[[str], str]) -> None:
    output = Path(args.output).expanduser()
    if output.exists():
        raise SessionError(f"Output already exists: {output}")
    if args.path:
        path = Path(args.path)
    elif sys.stdin.isatty():
        path = _choose_path(ask)
    else:
        raise SessionError("Pass a session path when running without an interactive terminal")
    session = parse_session(path)
    if args.line is not None:
        line = args.line
    elif sys.stdin.isatty():
        line = _choose_line(session, ask)
    else:
        raise SessionError("Pass --line N when running without an interactive terminal")
    report = build_draft(session, line)
    try:
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(report.markdown)
    except FileExistsError as exc:
        raise SessionError(f"Output already exists: {output}") from exc
    except OSError as exc:
        raise SessionError(f"Cannot write report: {exc}") from exc
    print(f"Created {output} ({report.redactions} automatic redactions; review before sharing).")
    if session.malformed_lines:
        print(f"Skipped {session.malformed_lines} malformed JSONL line(s).")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="session2issue", description="Create a reviewable issue draft from a Codex session")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="List recent local Codex sessions")
    listing.add_argument("--limit", type=int, default=20)
    draft = commands.add_parser("draft", help="Create a local issue draft")
    draft.add_argument("path", nargs="?", help="Codex rollout JSONL path; omit to choose a recent session")
    draft.add_argument("--line", type=int, help="JSONL line to report; omit for interactive selection")
    draft.add_argument("--output", "-o", default="issue.md")
    ai = commands.add_parser("summarize", help="Optionally improve title and summary with OpenAI API")
    ai.add_argument("source", help="A reviewed Session2Issue Markdown draft")
    ai.add_argument("--output", "-o", default="issue.ai.md")
    ai.add_argument("--model", default="gpt-6-luna")
    return parser


def main(argv: list[str] | None = None, *, ask: Callable[[str], str] = input) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            paths = _sessions(args.limit)
            if not paths:
                print("No Codex sessions found. You can pass a JSONL path to 'draft'.")
        elif args.command == "draft":
            _draft(args, ask)
        elif args.command == "summarize":
            summarize(Path(args.source).expanduser(), Path(args.output).expanduser(), args.model, confirm=ask)
            print(f"Created {args.output}. Verify the AI-assisted wording before posting.")
    except (SessionError, OSError) as exc:
        print(f"session2issue: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
