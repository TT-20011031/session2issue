# Contributing

Thank you for helping improve Session2Issue. Please open an issue before a large change so we can agree on the behavior.

## Local checks

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m compileall -q src
```

Keep the offline draft path free of network calls. Add synthetic JSONL fixtures for parser bugs; do not commit real session transcripts or credentials. Tests for the optional AI command must use a fake client and never require an API key.

Please include the user-visible behavior and a regression case in pull requests. The README and Chinese guide should stay aligned when commands change.
