"""Build a bounded Markdown report from a selected transcript line."""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from pathlib import Path

from .redact import Redactor
from .context import fenced
from .session import Event, Session, SessionError, paired_call


# Keep the existing file marker readable by title/summary-only clients.
MARKER = "<!-- session2issue:v0.1 -->"


@dataclass(slots=True)
class Draft:
    markdown: str
    redactions: int
    sections: dict[str, str] = field(default_factory=dict)


def write_report(path: Path, text: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
    except FileExistsError as exc:
        raise SessionError(f"Output already exists: {path}") from exc
    except OSError as exc:
        raise SessionError(f"Cannot write report: {exc}") from exc


def _one_line(value: str, limit: int = 180) -> str:
    value = " ".join(value.split())
    return value[: limit - 1] + "…" if len(value) > limit else value


def _snippet(value: str, max_chars: int = 2000, max_lines: int = 20) -> str:
    lines = value.splitlines()[:max_lines]
    joined = "\n".join(lines)[:max_chars]
    return joined or "[No text in this record]"


def _event_label(event: Event, session: Session, redactor: Redactor) -> str:
    text = _one_line(redactor.clean(event.text))
    if event.kind == "tool_call":
        return f"Called `{redactor.clean(event.name or 'tool')}`: {text}"
    if event.kind == "tool_output":
        call = paired_call(session, event)
        name = call.name if call else "tool"
        return f"Result from `{redactor.clean(name)}`: {text}"
    return f"{event.kind.title()}: {text}"


def _table_cell(value: str) -> str:
    return value.replace("|", "\\|")


def build_draft(session: Session, selected_line: int) -> Draft:
    if selected_line not in session.valid_lines:
        raise SessionError(f"Line {selected_line} is not a valid JSONL record")
    redactor = Redactor()
    selected = next((event for event in session.events if event.line == selected_line), None)
    if selected is None:
        selected = Event(selected_line, "", "record", "No displayable text in the selected record")
    before = [event for event in session.events if event.line < selected_line]
    after = [event for event in session.events if event.line > selected_line]
    nearby = before[-5:] + [selected] + after[:2]
    paired = paired_call(session, selected)
    if paired and paired not in nearby:
        nearby.insert(0, paired)
    task = next((event.text for event in reversed(before) if event.kind == "user" and event.text.strip()), "")
    evidence = redactor.clean(selected.text)
    if selected.kind == "tool_call":
        evidence = f"Tool call: {redactor.clean(selected.name)}\n{evidence}"
    elif selected.kind == "tool_output" and paired:
        evidence = f"Tool: {redactor.clean(paired.name)}\nInput: {_snippet(redactor.clean(paired.text), 500, 5)}\nOutput:\n{evidence}"
    elif selected.kind == "record":
        evidence = "Selected record contains no displayable message or tool text. Inspect the original session at the line above."
    timeline = "\n".join(f"| {event.line} | {_table_cell(_event_label(event, session, redactor))} |" for event in nearby)
    metadata = session.metadata
    cwd = _one_line(redactor.clean(str(metadata.get("cwd") or "[Not recorded]")), 512).replace("`", "'")
    cli_version = _one_line(redactor.clean(str(metadata.get("cli_version") or "[Not recorded]")), 512).replace("`", "'")
    source = _one_line(redactor.clean(str(metadata.get("source") or metadata.get("originator") or "[Not recorded]")), 512).replace("`", "'")
    recorded_at = _one_line(redactor.clean(str(metadata.get("timestamp") or selected.timestamp or "[Not recorded]")), 512).replace("`", "'")
    task_text = _snippet(redactor.clean(task), 500, 5) if task else "[Not found; add the original task]"
    evidence_text = _snippet(evidence)
    sections = {
        "Original task": f"## Original task\n\n{fenced(task_text)}",
        "Evidence": (
            f"## Evidence\n\nSelected session line: `{selected_line}`\n\n"
            "Source file: `[local Codex transcript; path omitted]`\n\n"
            f"{fenced(evidence_text)}\n\n### Nearby timeline\n\n"
            "| JSONL line | Recorded event |\n| ---: | --- |\n" + timeline
        ),
        "Environment": (
            f"## Environment\n\n- Codex version: `{cli_version}`\n"
            f"- Session source: `{source}`\n- Recorded at: `{recorded_at}`\n"
            f"- Session working directory: `{cwd}`\n"
            f"- Reporting machine OS: `{platform.system()}` (may differ from the session host)"
        ),
    }
    summary = "A Codex session encountered the event shown in Evidence while working on the task below."
    report = f"""{MARKER}
# [Describe the failure]

## Summary

{summary}

{sections['Original task']}

## Expected behavior

[TODO: Describe what you expected. Verify this independently of the transcript.]

## Actual behavior

The selected event occurred at JSONL line {selected_line}. The excerpt below is quoted from the session record.

## Steps to reproduce

[TODO: Add and verify the steps needed to reproduce the issue.]

{sections['Evidence']}

{sections['Environment']}

## Privacy review

- Automatic redactions before excerpt clipping: **REDaction_COUNT**.
- [ ] Review prompts, commands, paths, and tool outputs for private information.
- [ ] Check the quoted evidence against the original session.
- [ ] Confirm the expected behavior and reproduction steps before posting.

Automatic redaction is best-effort and cannot guarantee this draft is safe to share.
"""
    report = report.replace("REDaction_COUNT", str(redactor.total))
    return Draft(report, redactor.total, sections)
