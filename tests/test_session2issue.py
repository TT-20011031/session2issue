from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from session2issue.ai import summarize
from session2issue.cli import main
from session2issue.report import build_draft
from session2issue.session import SessionError, candidates, discover_sessions, parse_session


def record(kind: str, payload: dict, timestamp: str = "2026-10-01T00:00:00Z") -> str:
    return json.dumps({"timestamp": timestamp, "type": kind, "payload": payload}, ensure_ascii=False)


def sample_lines() -> list[str]:
    return [
        record("session_meta", {"cli_version": "0.1.0", "cwd": r"C:\Users\Alice\private-project", "source": "cli"}),
        record("response_item", {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Build this app; contact alice@example.com"}]}),
        record("response_item", {"type": "function_call", "name": "exec_command", "call_id": "call-1", "arguments": '{"cmd":"run tests"}'}),
        record("response_item", {"type": "function_call_output", "call_id": "call-1", "output": json.dumps({"exit_code": 1, "output": "Fatal error: sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"})}),
        record("response_item", {"type": "custom_tool_call", "name": "browser", "call_id": "call-2", "input": "open page"}),
        record("response_item", {"type": "custom_tool_call_output", "call_id": "call-2", "output": [{"type": "text", "text": "Error: request failed"}]}),
    ]


class SessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_session(self, lines: list[str] | None = None) -> Path:
        path = self.root / "rollout-demo.jsonl"
        path.write_text("\n".join(lines if lines is not None else sample_lines()) + "\n", encoding="utf-8")
        return path

    def test_parses_string_and_array_outputs_and_redacts_report(self) -> None:
        session = parse_session(self.write_session())
        self.assertEqual([event.line for event in candidates(session)], [4, 6])
        draft = build_draft(session, 4)
        self.assertIn("JSONL line 4", draft.markdown)
        self.assertIn("exec_command", draft.markdown)
        self.assertIn("[REDACTED:openai_key]", draft.markdown)
        self.assertIn("[REDACTED:email]", draft.markdown)
        self.assertIn("<HOME>", draft.markdown)
        self.assertNotIn("Alice", draft.markdown)
        self.assertNotIn("alice@example.com", draft.markdown)
        self.assertGreaterEqual(draft.redactions, 3)

    def test_manual_line_works_without_error_and_malformed_line_is_skipped(self) -> None:
        path = self.write_session(["not json", *sample_lines()[:3]])
        session = parse_session(path)
        self.assertEqual(session.malformed_lines, 1)
        self.assertFalse(candidates(session))
        draft = build_draft(session, 3)
        self.assertIn("Selected session line: `3`", draft.markdown)

    def test_empty_or_invalid_file_fails_clearly(self) -> None:
        path = self.write_session(["broken"])
        with self.assertRaisesRegex(SessionError, "No valid JSONL"):
            parse_session(path)

    def test_discovers_active_and_archived_with_custom_codex_home(self) -> None:
        active = self.root / "sessions" / "2026" / "rollout-one.jsonl"
        archived = self.root / "archived_sessions" / "rollout-two.jsonl"
        active.parent.mkdir(parents=True)
        archived.parent.mkdir(parents=True)
        active.write_text(sample_lines()[0], encoding="utf-8")
        archived.write_text(sample_lines()[0], encoding="utf-8")
        with patch.dict(os.environ, {"CODEX_HOME": str(self.root)}):
            self.assertEqual(set(discover_sessions()), {active, archived})

    def test_cli_draft_refuses_to_overwrite(self) -> None:
        path = self.write_session()
        target = self.root / "issue.md"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["draft", str(path), "--line", "4", "--output", str(target)]), 0)
            self.assertEqual(main(["draft", str(path), "--line", "4", "--output", str(target)]), 2)
        self.assertIn("## Evidence", target.read_text(encoding="utf-8"))

    def test_cli_list_empty_directory(self) -> None:
        output = io.StringIO()
        with patch.dict(os.environ, {"CODEX_HOME": str(self.root)}), contextlib.redirect_stdout(output):
            self.assertEqual(main(["list"]), 0)
        self.assertIn("No Codex sessions", output.getvalue())

    def test_cli_interactive_selection_accepts_a_non_error_line(self) -> None:
        path = self.write_session()
        target = self.root / "manual.md"
        answers = iter(["line 3"])
        fake_stdin = type("InteractiveInput", (), {"isatty": lambda self: True})()
        output = io.StringIO()
        with patch("sys.stdin", fake_stdin), contextlib.redirect_stdout(output):
            self.assertEqual(main(["draft", str(path), "--output", str(target)], ask=lambda _: next(answers)), 0)
        self.assertIn("Possible failure events", output.getvalue())
        self.assertIn("Selected session line: `3`", target.read_text(encoding="utf-8"))


class AITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        log = self.root / "rollout-demo.jsonl"
        log.write_text("\n".join(sample_lines()) + "\n", encoding="utf-8")
        self.source = self.root / "issue.md"
        self.source.write_text(build_draft(parse_session(log), 4).markdown, encoding="utf-8")

    def test_ai_receives_only_reviewed_draft_and_changes_only_wording(self) -> None:
        calls: list[dict] = []

        class Responses:
            def create(self, **kwargs):
                calls.append(kwargs)
                return type("Response", (), {"output_text": json.dumps({"title": "Codex command failed during tests", "summary": "The test command returned a nonzero exit code."})})()

        class Client:
            responses = Responses()

        target = self.root / "issue.ai.md"
        summarize(self.source, target, confirm=lambda _: "y", client_factory=Client)
        before = self.source.read_text(encoding="utf-8")
        after = target.read_text(encoding="utf-8")
        self.assertEqual(calls[0]["input"], before)
        self.assertFalse(calls[0]["store"])
        self.assertIn("# Codex command failed during tests", after)
        self.assertIn("AI-assisted wording", after)
        self.assertEqual(after.split("## Evidence", 1)[1], before.split("## Evidence", 1)[1])

    def test_decline_ai_leaves_no_new_file(self) -> None:
        target = self.root / "issue.ai.md"
        with self.assertRaisesRegex(SessionError, "cancelled"):
            summarize(self.source, target, confirm=lambda _: "n", client_factory=lambda: None)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
