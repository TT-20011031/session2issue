"""Read the useful, non-reasoning parts of a Codex JSONL transcript."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any

from .redact import Redactor


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
    total_lines: int = 0


@dataclass(slots=True)
class SessionPreview:
    path: Path
    project: str
    title: str
    title_source: str


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


def task_excerpt(text: str) -> str:
    """Skip context-only user messages injected by Codex."""
    text = text.strip()
    if "## My request:" in text:
        return text.split("## My request:", 1)[1].strip()
    if text.startswith("<environment_context>") and "</environment_context>" in text:
        text = text.split("</environment_context>", 1)[1].strip()
    if text.startswith(("# AGENTS.md instructions", "<environment_context>", "<permissions instructions>", "<INSTRUCTIONS>", "<skill>")):
        return ""
    return text


def _preview_metadata(path: Path) -> tuple[dict[str, Any], str]:
    """Read a bounded prefix, never a whole transcript, for session selection."""
    metadata: dict[str, Any] = {}
    task = ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            prefix = stream.read(1024 * 1024)
    except OSError:
        return metadata, task
    for raw in prefix.splitlines():
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
            continue
        payload = record["payload"]
        if record.get("type") == "session_meta":
            metadata.update(payload)
        elif record.get("type") == "response_item" and payload.get("type") == "message" and payload.get("role") == "user":
            task = task_excerpt(_message_text(payload.get("content")))
        elif record.get("type") == "event_msg" and payload.get("type") == "user_message":
            task = task_excerpt(_message_text(payload.get("message")))
        if task:
            break
    return metadata, task


def session_previews(paths: list[Path]) -> list[SessionPreview]:
    """Prefer Codex's local session index titles; fall back to task excerpts."""
    details = [_preview_metadata(path) for path in paths]
    ids = [str(meta.get("id") or meta.get("session_id") or "") for meta, _ in details]
    titles: dict[str, str] = {}
    wanted = set(ids) - {""}
    try:
        with (codex_home() / "session_index.jsonl").open("r", encoding="utf-8", errors="replace") as stream:
            for raw in stream:
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(item, dict):
                    continue
                session_id, title = item.get("id"), item.get("thread_name")
                if isinstance(session_id, str) and session_id in wanted and isinstance(title, str) and title.strip():
                    titles[session_id] = title.strip()
    except OSError:
        pass  # Older installations may not have an index; transcripts still work.
    previews = []
    for path, session_id, (metadata, task) in zip(paths, ids, details):
        cwd = metadata.get("cwd")
        # PureWindowsPath also understands forward slashes on Linux.
        project = PureWindowsPath(Redactor().clean(cwd)).name if isinstance(cwd, str) and cwd else ""
        title = titles.get(session_id, "")
        if title:
            source = "title"
        elif task:
            title, source = task, "task excerpt"
        else:
            title, source = "No title or task excerpt available", "unavailable"
        previews.append(SessionPreview(path, project or "Unknown project", title, source))
    return previews


_MEDIA_TYPES = {"image", "input_image", "image_url", "audio", "input_audio"}
_OMIT_MEDIA = object()


def _without_media(value: Any) -> Any:
    if isinstance(value, dict):
        if isinstance(value.get("type"), str) and value["type"] in _MEDIA_TYPES:
            return _OMIT_MEDIA
        return {key: clean for key, item in value.items() if (clean := _without_media(item)) is not _OMIT_MEDIA}
    if isinstance(value, list):
        return [clean for item in value if (clean := _without_media(item)) is not _OMIT_MEDIA]
    return value


def _as_text(value: Any) -> str:
    if value is _OMIT_MEDIA:
        return ""
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                parsed = json.loads(value)
            except ValueError:
                parsed = None
            if isinstance(parsed, (dict, list)) and (clean := _without_media(parsed)) != parsed:
                return _as_text(clean)
        return value
    if isinstance(value, list):
        return "\n".join(_as_text(item) for item in value if item is not None)
    if isinstance(value, dict):
        if value.get("type") in ("image", "input_image", "image_url", "audio", "input_audio"):
            return ""
        if isinstance(value.get("text"), str):
            return value["text"]
        return json.dumps(_without_media(value), ensure_ascii=False)
    return "" if value is None else str(value)


def _message_text(value: Any) -> str:
    """Messages contain text and possibly image/audio blocks; keep only text."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(text for item in value if (text := _message_text(item)))
    if isinstance(value, dict) and value.get("type") not in ("image", "input_image", "image_url", "audio", "input_audio"):
        return value.get("text", "") if isinstance(value.get("text"), str) else ""
    return ""


def paired_call(session: Session, event: Event) -> Event | None:
    """Repeated call IDs must never match a call that happened after a result."""
    if event.kind != "tool_output" or not event.call_id:
        return None
    return next((call for call in reversed(session.events)
                 if call.line < event.line and call.kind == "tool_call" and call.call_id == event.call_id), None)


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
        text = _message_text(payload.get("content"))
        if role == "user":
            text = task_excerpt(text)
        return Event(line, timestamp, role if text.strip() else "record", text)
    if kind in ("function_call", "custom_tool_call"):
        arguments = payload.get("arguments", payload.get("input"))
        return Event(line, timestamp, "tool_call", _as_text(arguments), _as_text(payload.get("name")), call_id)
    if kind in ("function_call_output", "custom_tool_call_output"):
        output = payload.get("output")
        text = _as_text(output)
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
                session.total_lines = number
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
