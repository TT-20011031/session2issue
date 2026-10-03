"""Console interface for Session2Issue."""

from __future__ import annotations

import argparse
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import __version__
from .ai import summarize
from .compose import compose
from .context import build_context
from .redact import Redactor
from .report import build_draft, write_report
from .session import Session, SessionError, candidates, codex_home, discover_sessions, parse_session, session_previews


def _preview(text: str, limit: int, redactor: Redactor) -> str:
    # Mask before shortening so a truncated credential cannot escape masking.
    text = redactor.clean(text)
    text = "".join(char if not unicodedata.category(char).startswith("C") else " " for char in text)
    text = " ".join(text.split())
    return text[:limit - 1] + "…" if len(text) > limit else text


def _sessions(limit: int = 20, *, show_paths: bool = False) -> list[Path]:
    paths = discover_sessions(limit)
    redactor = Redactor()
    for index, info in enumerate(session_previews(paths), start=1):
        path = info.path
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            modified = "unknown time"
        project = _preview(info.project, 40, redactor)
        title = _preview(info.title, 100, redactor)
        suffix = " [task excerpt]" if info.title_source == "task excerpt" else ""
        print(f"{index:>2}. {modified}  [{project}]")
        print(f"    {title}{suffix}")
        if show_paths:
            try:
                label = path.relative_to(codex_home())
            except ValueError:
                label = path
            print(f"    File: {_preview(str(label), 300, redactor)}")
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
        print("Possible problem events (choose a number or enter 'line N'):")
        print("These are error signals, not a diagnosis. Some may already be fixed later in the session.")
        for index, event in enumerate(found[:30], start=1):
            preview = _preview(event.text, 180, redactor)
            print(f"{index:>2}. line {event.line}: {preview}")
        if len(found) > 30:
            print(f"{len(found) - 30} more candidates omitted; use 'line N' to select one.")
    else:
        print("No obvious error signal found. For an incorrect result, enter 'line N' for the relevant record.")
    print("Choose an event only if it relates to a problem you want to report; Ctrl+C cancels.")
    raw = ask("Event to report: ").strip().lower()
    if raw.startswith("line ") and raw[5:].strip().isdecimal():
        return int(raw[5:].strip())
    if raw.isdecimal() and 1 <= int(raw) <= min(len(found), 30):
        return found[int(raw) - 1].line
    raise SessionError("Choose a candidate number or enter 'line N'")


def _draft(args: argparse.Namespace, ask: Callable[[str], str]) -> None:
    output = Path(args.output).expanduser()
    backup = output.with_name(output.stem + ".local" + (output.suffix or ".md"))
    preview = output.with_name(output.stem + ".context.md")
    for target in (output, backup, preview) if args.ai else (output,):
        if target.exists():
            raise SessionError(f"Output already exists: {target}")
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
    local_target = backup if args.ai else output
    write_report(local_target, report.markdown)
    print(f"Created {local_target} ({report.redactions} automatic redactions; review before sharing).")
    if session.malformed_lines:
        print(f"Skipped {session.malformed_lines} malformed JSONL line(s).")
    if not args.ai:
        return
    try:
        context = build_context(session, line, args.context_lines)
        write_report(preview, context.text)
        print(f"Review the exact API snapshot: {preview.resolve()}")
        print(f"JSONL window {context.start_line}:{context.end_line}; {len(context.events)} events; "
              f"{context.omitted_events} omitted in window; {context.outside_events} outside window; "
              f"{context.redactions} redactions; truncated lines: {context.truncated_lines or 'none'}.")
        print("Read the preview before confirming. It contains conversation context, not just the local draft. "
              "Redaction is best-effort; API use may incur charges.")

        def confirm_send(prompt: str) -> str:
            answer = ask(prompt)
            if answer.strip().lower() == "y":
                if preview.read_text(encoding="utf-8") != context.text:
                    raise SessionError("Preview changed; no request was sent. Regenerate with a new output name or context range")
                if output.exists():
                    raise SessionError(f"Output already exists: {output}")
            return answer

        compose(session, context, output, args.model or "gpt-6-luna", confirm=confirm_send)
        print(f"Created {output}. Edit and verify the complete AI draft before posting.")
    except (SessionError, OSError, KeyboardInterrupt):
        print(f"Local backup retained: {backup.resolve()}")
        if preview.exists():
            print(f"Context preview retained: {preview.resolve()}")
        raise


def _line_range(raw: str) -> tuple[int, int]:
    parts = raw.split(":")
    if len(parts) != 2 or not all(part.isdecimal() for part in parts):
        raise argparse.ArgumentTypeError("Use START:END with positive JSONL line numbers")
    start, end = map(int, parts)
    if not 1 <= start <= end:
        raise argparse.ArgumentTypeError("Context range must satisfy 1 <= START <= END")
    return start, end


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="session2issue", description="Create a reviewable issue draft from a Codex session")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="List recent local Codex sessions")
    listing.add_argument("--limit", type=int, default=20)
    listing.add_argument("--paths", action="store_true", help="Also show transcript file paths")
    draft = commands.add_parser("draft", help="Create a local issue draft")
    draft.add_argument("path", nargs="?", help="Codex rollout JSONL path; omit to choose a recent session")
    draft.add_argument("--line", type=int, help="JSONL line to report; omit for interactive selection")
    draft.add_argument("--output", "-o", default="issue.md")
    draft.add_argument("--ai", action="store_true", help="Generate a complete draft with confirmed OpenAI API submission")
    draft.add_argument("--model", help="AI model (default: gpt-6-luna); requires --ai")
    draft.add_argument("--context-lines", type=_line_range, help="Inclusive START:END JSONL context range; requires --ai")
    ai = commands.add_parser("summarize", help="Optionally improve title and summary with OpenAI API")
    ai.add_argument("source", help="A reviewed Session2Issue Markdown draft")
    ai.add_argument("--output", "-o", default="issue.ai.md")
    ai.add_argument("--model", default="gpt-6-luna")
    return parser


def main(argv: list[str] | None = None, *, ask: Callable[[str], str] = input) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    if args.command == "draft" and not args.ai and (args.model is not None or args.context_lines is not None):
        parser.error("--model and --context-lines require --ai")
    try:
        if args.command == "list":
            paths = _sessions(args.limit, show_paths=args.paths)
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
    except KeyboardInterrupt:
        print("\nsession2issue: Cancelled.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
