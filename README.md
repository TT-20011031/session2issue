# Session2Issue

**Turn a failed Codex session into a GitHub issue draft you can verify.**

Session2Issue is a local Python CLI. It finds a relevant part of a Codex JSONL transcript, quotes a bounded amount of evidence, and writes an English Markdown report. It leaves expected behavior, reproduction steps, and root-cause judgment to you.

[简体中文说明](README.zh-CN.md)

## Why?

A coding-agent session may contain dozens of tool calls and pages of output. Pasting the entire transcript into an issue is hard to read and may expose private data. Session2Issue gives you a short, editable starting point while keeping the original transcript unchanged.

## Install from source

Requires Python 3.11 or newer. Clone this repository, then run from its root:

```bash
uv tool install .
session2issue --version
```

If you use a Python environment with pip, `python -m pip install .` also works. For development, use `python -m pip install -e .` or `uv pip install -e .` inside a virtual environment. The basic CLI needs no API key and makes no network request.

## Quick start

```bash
session2issue list
session2issue draft --output issue.md
```

The draft command lets you choose a recent session and a likely failure. You can also type `line N` to choose any JSONL record, including a failure the heuristics did not recognize. If you already know the file and line, use:

```bash
session2issue draft path/to/rollout.jsonl --line 42 --output issue.md
```

The session list searches `$CODEX_HOME/sessions` and `$CODEX_HOME/archived_sessions`; `CODEX_HOME` defaults to `~/.codex`. When no terminal is available, pass both the path and `--line`. Existing output files are never overwritten.

### Try a synthetic example

```bash
session2issue draft examples/sample.jsonl --line 4 --output sample-issue.md
```

The example's raw result is a failed test command:

```text
FAILED (errors=1): ModuleNotFoundError: No module named 'demo'
```

The generated report turns it into a reviewable issue outline:

```markdown
## Original task
Run the project's test suite and report whether it passes.

## Actual behavior
The selected event occurred at JSONL line 4.

## Steps to reproduce
[TODO: Add and verify the steps needed to reproduce the issue.]

## Evidence
Selected session line: `4`
```

The report includes nearby events, source line numbers, available Codex metadata, and a privacy checklist. It does not diagnose the root cause or submit an issue for you.

## Optional AI wording

After reviewing and editing `issue.md`, you can ask the OpenAI API to improve **only the title and short summary**. This creates a separate file; the evidence and TODO fields remain unchanged.

```bash
uv tool install '.[ai]'
# Set OPENAI_API_KEY in your shell using your platform's normal method.
session2issue summarize issue.md --output issue.ai.md
```

In a pip-managed environment, use `python -m pip install '.[ai]'` instead.

The command shows the input size and asks for confirmation before sending the reviewed draft to the API. It defaults to `gpt-6-luna`; use `--model` to choose another supported model. API use may incur charges. The request sets `store=False`, which disables stored response state; it is **not** a promise that API processing retains no data. See [OpenAI's data controls](https://developers.openai.com/api/docs/guides/your-data).

## Privacy and limitations

- Draft generation runs locally and never modifies the source transcript.
- Automatic masking covers common credential shapes, email addresses, and home-directory paths. It is best-effort; **review every report before sharing**.
- Errors are suggested using simple signals such as nonzero exit codes and error text. Use `line N` when a failure has no explicit error.
- Some Codex records have no displayable message or tool text. The draft will point to the selected line and ask you to inspect the source.
- Only Codex JSONL transcripts are supported in v0.1. No account, service, browser UI, or automatic GitHub posting is required.

## Development

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [MIT](LICENSE).
