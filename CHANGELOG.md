# Changelog

## 0.2.0

- Show project directory names and saved Codex conversation titles in session selection; fall back to task excerpts.
- Add optional complete issue generation with `draft --ai`, inclusive `--context-lines START:END` and `--model`.
- Save an offline backup and exact redacted context preview before confirmed API submission.
- Label recorded facts, conversation claims, hypotheses and missing information; validate cited source lines.
- Include later attempts and verification within a bounded context window.
- Keep original evidence and environment sections under program control, including logs containing Markdown headings or fences.
- Mask credentials before excerpt clipping and associate results with preceding tool calls.
- Preserve local files on AI failures and cancellation; retain offline draft and title/summary-only commands.
- Add synthetic examples and mock API tests; never include real sessions or require a live API key in CI.
