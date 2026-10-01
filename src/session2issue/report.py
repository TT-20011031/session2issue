"""Build a bounded Markdown report from a selected transcript line."""

from __future__ import annotations

import platform
from dataclasses import dataclass

from .redact import Redactor
from .session import Event, Session, SessionError


MARKER = "<!-- session2issue:v0.1 -->"


@dataclass(slots=True)
class Draft:
    markdown: str
    redactions: int


def _one_line(value: str, limit: int = 180) -> str:
    value = " ".join(value.split())
    return value[: limit - 1] + "…" if len(value) > limit else value


def _snippet(value: str, max_chars: int = 2000, max_lines: int = 20) -> str:
    lines = value.splitlines()[:max_lines]
    joined = "\n".join(lines)[:max_chars]
    return joined or "[No text in this record]"


def _event_label(event: Event, calls: dict[str, Event]) -> str:
    if event.kind == "tool_call":
        return f"Called `{event.name or 'tool'}`: {_one_line(event.text)}"
    if event.kind == "tool_output":
        call = calls.get(event.call_id)
        name = call.name if call else "tool"
        return f"Result from `{name}`: {_one_line(event.text)}"
    return f"{event.kind.title()}: {_one_line(event.text)}"


def _table_cell(value: str) -> str:
    return value.replace("|", "\\|")


def build_draft(session: Session, selected_line: int) -> Draft:
    if selected_line not in session.valid_lines:
        raise SessionError(f"Line {selected_line} is not a valid JSONL record")
    redactor = Redactor()
    calls = {event.call_id: event for event in session.events if event.kind == "tool_call" and event.call_id}
    selected = next((event for event in session.events if event.line == selected_line), None)
    if selected is None:
        selected = Event(selected_line, "", "record", "No displayable text in the selected record")
    before = [event for event in session.events if event.line < selected_line]
    after = [event for event in session.events if event.line > selected_line]
    nearby = before[-5:] + [selected] + after[:2]
    paired = calls.get(selected.call_id) if selected.kind == "tool_output" else None
    if paired and paired not in nearby:
        nearby.insert(0, paired)
    task = next((event.text for event in reversed(before) if event.kind == "user" and event.text.strip()), "")
    evidence = selected.text
    if selected.kind == "tool_call":
        evidence = f"Tool call: {selected.name}\n{selected.text}"
    elif selected.kind == "tool_output" and paired:
        evidence = f"Tool: {paired.name}\nInput: {_snippet(paired.text, 500, 5)}\nOutput:\n{selected.text}"
    elif selected.kind == "record":
        evidence = "Selected record contains no displayable message or tool text. Inspect the original session at the line above."
    timeline = "\n".join(f"| {event.line} | {_table_cell(redactor.clean(_event_label(event, calls)))} |" for event in nearby)
    metadata = session.metadata
    cwd = redactor.clean(str(metadata.get("cwd") or "[Not recorded]"))
    cli_version = redactor.clean(str(metadata.get("cli_version") or "[Not recorded]"))
    source = redactor.clean(str(metadata.get("source") or metadata.get("originator") or "[Not recorded]"))
    recorded_at = redactor.clean(str(metadata.get("timestamp") or selected.timestamp or "[Not recorded]"))
    task_text = redactor.clean(_snippet(task, 500, 5)) if task else "[Not found; add the original task]"
    task_text = task_text.replace("```", "'''")
    evidence_text = redactor.clean(_snippet(evidence))
    evidence_text = evidence_text.replace("```", "'''")
    summary = "A Codex session encountered the event shown in Evidence while working on the task below."
    report = f"""{MARKER}
# [Describe the failure]

## Summary

{summary}

## Original task

```text
{task_text}
```

## Expected behavior

[TODO: Describe what you expected. Verify this independently of the transcript.]

## Actual behavior

The selected event occurred at JSONL line {selected_line}. The excerpt below is quoted from the session record.

## Steps to reproduce

[TODO: Add and verify the steps needed to reproduce the issue.]

## Evidence

Selected session line: `{selected_line}`  
Source file: `[local Codex transcript; path omitted]`

```text
{evidence_text}
```

### Nearby timeline

| JSONL line | Recorded event |
| ---: | --- |
{timeline}

## Environment

- Codex version: `{cli_version}`
- Session source: `{source}`
- Recorded at: `{recorded_at}`
- Session working directory: `{cwd}`
- Reporting machine OS: `{platform.system()}` (may differ from the session host)

## Privacy review

- Automatic redactions in this draft: **REDaction_COUNT**.
- [ ] Review prompts, commands, paths, and tool outputs for private information.
- [ ] Check the quoted evidence against the original session.
- [ ] Confirm the expected behavior and reproduction steps before posting.

Automatic redaction is best-effort and cannot guarantee this draft is safe to share.
"""
    report = report.replace("REDaction_COUNT", str(redactor.total))
    return Draft(report, redactor.total)
