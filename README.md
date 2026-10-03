# Session2Issue

**Turn a problem encountered during a Codex task into a GitHub issue draft you can verify.**

Session2Issue is a Python CLI for Codex JSONL transcripts. Generate an offline evidence outline, or use optional AI generation to fill an English issue draft from related conversation context. Review and edit the facts, reproduction suggestions and hypotheses before sharing.

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

With uv, you can also run a pinned release without cloning:

```bash
uvx --from "git+https://github.com/TT-20011031/session2issue@v0.2.0" session2issue list
```

## Quick start

```bash
session2issue list
session2issue draft --output issue.md
```

The session picker shows the working-directory project name and Codex's saved conversation title:

```text
 1. 2026-10-03 10:35  [checkout-service]
    Fix checkout validation
 2. 2026-10-02 15:20  [demo-app]
    Run the test suite [task excerpt]
```

Titles come from the local `session_index.jsonl` when available. Without a saved title, the picker uses the first task excerpt in a bounded transcript prefix and labels it accordingly. Dates reflect transcript file modification times. Use `session2issue list --paths` to also see filenames, or `--limit 50` to see more sessions. Displayed titles and excerpts receive the same best-effort masking as draft content.

The draft command lets you choose a recent session and an event to report. You can also type `line N` to choose any JSONL record, including a problem the heuristics did not recognize. If you already know the file and line, use:

```bash
session2issue draft path/to/rollout.jsonl --line 42 --output issue.md
```

The session list searches `$CODEX_HOME/sessions` and `$CODEX_HOME/archived_sessions`; `CODEX_HOME` defaults to `~/.codex`. When no terminal is available, pass both the path and `--line`. Existing output files are never overwritten.

### What counts as a problem?

Any problem encountered while Codex works on a task can be relevant: a command or test fails, a tool request times out, a dependency is missing, or the resulting code does not meet your requirements. The report can be used for the affected project, dependency, or tool.

Nonzero exits and error text are **candidate evidence**, not a diagnosis of a Codex bug. Errors fixed during normal debugging may need no issue. Choose an event only when it relates to a problem you actually want to report; `Ctrl+C` cancels selection. An incorrect result may have no error signal, so select its relevant record with `line N` and explain the expected and actual behavior yourself.

If you have no recent problem to report, use the synthetic example below to try the workflow.

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

The offline report includes nearby events, source line numbers, available Codex metadata, and a privacy checklist. Expected behavior and reproduction steps remain editable placeholders in this mode.

## Complete AI draft (optional)

Install the optional dependency, set `OPENAI_API_KEY` in your shell, then run:

```bash
uv tool install --force '.[ai]'
session2issue draft --ai --output issue.md
```

For a local trial without installing the command globally:

```bash
uvx --refresh --from '.[ai]' session2issue draft examples/sample.jsonl --line 4 --ai --output issue-trial.md
```

The flow selects a session and problem, saves a local backup and context preview, then asks you to confirm API submission. **Read the preview before entering `y`.** The command generates these files:

| File | Content |
| --- | --- |
| `issue.local.md` | Offline evidence outline; retained even if the AI step fails |
| `issue.context.md` | Exact redacted conversation snapshot that will be sent |
| `issue.md` | Complete AI-assisted draft, created after a valid response |

The complete draft fills the title, summary, task goal, expected and actual behavior, reproduction draft, attempted fixes, outcome, possible causes and questions to confirm. It distinguishes:

- **Recorded fact:** directly supported by tool calls or results.
- **Reported in conversation:** a user or assistant's statement requiring verification.
- **Hypothesis / suggestion:** an interpretation or proposed step requiring user verification.
- **Not recorded:** information the user needs to supply.

An assistant saying “fixed” is a reported claim. A verified outcome needs later tool evidence, and still requires you to check what was actually tested. Citations identify included JSONL lines; they cannot guarantee that an AI interpretation is correct. Original task excerpts, evidence and environment fields are rendered by the program.

See the [complete illustrative report](examples/sample.ai.md). It is rendered from a [mock AI response](examples/sample.ai.json) over the synthetic session, **not a live model result**. Additional samples cover [later verification](examples/resolved.jsonl), [an unverified fix claim](examples/claimed-fix.jsonl) and [an incorrect answer with no tool error](examples/wrong-result.jsonl).

### Choose the context

The automatic window starts at the earliest of the last three actual user messages at or before the problem and includes the next two user turns and their replies, ending before a third following user message. Available file boundaries are used when fewer turns exist. The associated earlier tool call is also included in automatic mode.

For more control, supply an inclusive source range:

```bash
session2issue draft path/to/rollout.jsonl --line 42 --ai --context-lines 10:120 --model gpt-6-luna --output issue.md
```

The range must contain the selected line and stay inside the file. A call outside a manual range is marked missing. Context is limited to 40 events and 20,000 characters; ordinary events use up to 2,000 characters and the selected event up to 4,000. The problem, associated call, recent user requirements and final assistant summary take priority. Omitted events and truncated text are explicitly reported. System/developer instructions, injected environment messages, reasoning and image data are excluded.

`--model` and `--context-lines` on `draft` require `--ai`. The preview is a snapshot for inspection; editing it cancels submission rather than sending content different from the preview. To change the scope, rerun with another range and a new output name.

### Sending and failures

Complete generation sends **the context preview**, which contains more conversation material than the offline report. It sends no raw transcript file, unselected events or hidden instruction metadata. Masking occurs before clipping and remains best-effort. Counts describe masking operations before excerpt clipping.

AI commands require an interactive terminal. They default to `gpt-6-luna`, use a single request with a 60-second timeout, and do not automatically retry. API use may incur charges. Requests set `store=False`, which disables stored response state; it is **not** a promise of zero data retention during API processing. See [OpenAI's data controls](https://developers.openai.com/api/docs/guides/your-data).

Declining, cancelling, missing dependencies/key, request errors, refusals, incomplete responses and invalid citations retain any already-created local backup and preview. An existing target file blocks generation. AI errors return exit code 2; `Ctrl+C` returns 130. Reports are never posted automatically.

## Title and summary only

After reviewing and editing `issue.md`, you can ask the OpenAI API to improve **only the title and short summary**. This creates a separate file; the evidence and TODO fields remain unchanged.

```bash
uv tool install '.[ai]'
# Set OPENAI_API_KEY in your shell using your platform's normal method.
session2issue summarize issue.md --output issue.ai.md
```

In a pip-managed environment, use `python -m pip install '.[ai]'` instead.

This existing command sends only the reviewed Markdown draft and keeps the evidence and other sections unchanged. It uses the same model default and confirmation requirement as complete generation.

## Privacy and limitations

- Offline draft generation runs locally; AI generation is optional and explicitly confirmed. Source transcripts are never modified.
- Automatic masking covers common credential shapes, email addresses, and home-directory paths. It is best-effort; **review every report before sharing**.
- Errors are suggested using simple signals such as nonzero exit codes and error text. Use `line N` when a failure has no explicit error.
- Some Codex records have no displayable message or tool text. The draft will point to the selected line and ask you to inspect the source.
- Only Codex JSONL transcripts are supported in v0.2. Offline commands need no API account. Optional AI commands need an OpenAI API key.

## Development

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [MIT](LICENSE).
