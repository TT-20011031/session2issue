"""Read the useful, non-reasoning parts of a Codex JSONL transcript."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class SessionError(ValueError):
    """The requested session cannot produce a report."""


@dataclass(slots=True)
class Event:
    line: int
    timestamp: str
    kind: str
    text: str = ""
    name: str = ""
    call_id: str = ""
    is_error: bool = False


@dataclass(slots=True)
class Session:
    path: Path
    metadata: dict[str, Any] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    malformed_lines: int = 0
    valid_lines: set[int] = field(default_factory=set)


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()


def discover_sessions(limit: int = 20) -> list[Path]:
    """Find recent active and archived transcripts without opening their content."""
    if limit < 1:
        raise SessionError("--limit must be a positive integer")
    root = codex_home()
    paths: list[Path] = []
    for folder in (root / "sessions", root / "archived_sessions"):
        if folder.is_dir():
            paths.extend(folder.rglob("rollout-*.jsonl"))
    paths = [path for path in paths if path.is_file()]
    return sorted(paths, key=lambda path: path.stat().st_mtime, reverse=True)[:limit]


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_as_text(item) for item in value if item is not None)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def _output_is_error(value: Any, text: str) -> bool:
    if isinstance(value, dict):
        if value.get("isError") is True or value.get("is_error") is True:
            return True
        code = value.get("exit_code", value.get("exitCode"))
        if isinstance(code, int) and code != 0:
            return True
        for nested in value.values():
            if isinstance(nested, (dict, list, str)) and _output_is_error(nested, ""):
                return True
    elif isinstance(value, list):
        return any(_output_is_error(item, "") for item in value)
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, (dict, list)) and _output_is_error(parsed, ""):
            return True
        if re.search(r"\b(?:exit(?:ed)?\s*(?:code|status)\s*[:=]?\s*[1-9]\d*|traceback|fatal error)\b", value, re.I):
            return True
        if re.search(r"^\s*(?:error|failed):", value, re.I | re.M):
            return True
    return bool(
        re.search(r"\b(?:exit(?:ed)?\s*(?:code|status)\s*[:=]?\s*[1-9]\d*|traceback|fatal error)\b", text, re.I)
        or re.search(r"^\s*(?:error|failed):", text, re.I | re.M)
    )


def _event(line: int, record: dict[str, Any]) -> Event:
    payload = record.get("payload")
    timestamp = _as_text(record.get("timestamp"))
    if not isinstance(payload, dict):
        return Event(line, timestamp, "record")
    if record.get("type") != "response_item":
        return Event(line, timestamp, "record")
    kind = _as_text(payload.get("type"))
    call_id = _as_text(payload.get("call_id"))
    if kind == "message":
        role = _as_text(payload.get("role"))
        if role not in ("user", "assistant"):
            return Event(line, timestamp, "record")
        return Event(line, timestamp, role, _as_text(payload.get("content"))[:12000])
    if kind in ("function_call", "custom_tool_call"):
        arguments = payload.get("arguments", payload.get("input"))
        return Event(line, timestamp, "tool_call", _as_text(arguments)[:12000], _as_text(payload.get("name")), call_id)
    if kind in ("function_call_output", "custom_tool_call_output"):
        output = payload.get("output")
        text = _as_text(output)[:12000]
        return Event(line, timestamp, "tool_output", text, call_id=call_id, is_error=_output_is_error(output, text))
    return Event(line, timestamp, "record")


def parse_session(path: Path) -> Session:
    path = path.expanduser()
    if not path.is_file():
        raise SessionError(f"Session file not found: {path}")
    session = Session(path)
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for number, raw in enumerate(stream, start=1):
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError:
                    session.malformed_lines += 1
                    continue
                if not isinstance(record, dict):
                    session.malformed_lines += 1
                    continue
                session.valid_lines.add(number)
                if record.get("type") == "session_meta" and isinstance(record.get("payload"), dict):
                    session.metadata.update(record["payload"])
                event = _event(number, record)
                if event.kind != "record":
                    session.events.append(event)
    except OSError as exc:
        raise SessionError(f"Cannot read session file: {exc}") from exc
    if not session.valid_lines:
        raise SessionError("No valid JSONL records found in this file")
    return session


def candidates(session: Session) -> list[Event]:
    return [event for event in session.events if event.is_error]
