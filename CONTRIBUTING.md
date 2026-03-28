# Contributing to GSS

## How to Contribute

- **Spec changes:** Open an issue first. PRs against `spec/` must include updated examples.
- **New adapters:** Create under `adapters/`, follow existing structure, include tests.
- **Protocol templates:** Add to `protocols/templates/` or `protocols/examples/`, follow FORMAT.md.
- **Bug fixes:** PRs welcome for SDK, CLI, and validator. Include tests.

## Development Setup

```bash
git clone https://github.com/yourorg/global-support-standard.git
cd global-support-standard
python -m venv .venv && source .venv/bin/activate
pip install -e "./sdk[dev]" -e "./cli[dev]" -e "./validator[dev]"
pytest
```
