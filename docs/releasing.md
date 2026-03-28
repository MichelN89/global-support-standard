# Releasing

This document defines the production release flow for publishing `global-support-standard` to TestPyPI and PyPI.

## Preconditions (Required)

- All tests pass locally.
- Changelog updated in `CHANGELOG.md`.
- Version updated in `pyproject.toml` if a release is intended.
- CI is green on `main`.
- Release commit is merged to `main`.
- PyPI and TestPyPI projects are created and configured for Trusted Publishing.

## Local Verification

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
ruff check .
pytest
pytest --cov=src --cov-report=term-missing --cov-fail-under=80
python -m build
twine check dist/*
pip-audit
```

## Release Candidate Checklist

- [ ] Version in `pyproject.toml` matches intended release tag.
- [ ] `CHANGELOG.md` has release notes.
- [ ] `README.md` and docs reflect current behavior.
- [ ] `python -m build` produces valid `sdist` and `wheel`.
- [ ] `twine check dist/*` passes with no warnings.
- [ ] New CI checks are green (`lint-ruff`, tests matrix, coverage, package-check, dependency-audit).
- [ ] Tag matches project version (for example `v0.2.0`).

## Tag and Trigger Release

```bash
git checkout main
git pull
git tag v0.2.0
git push origin v0.2.0
```

The tag triggers `.github/workflows/release.yml`.

## GitHub Environments

Set up two environments in GitHub repository settings:

- `testpypi` (no manual approval required)
- `pypi` (recommended: required reviewer approval)

Trusted publishing should be configured for both indexes.

## Release Workflow Behavior

1. Build distributions once.
2. Publish to TestPyPI.
3. Publish to PyPI (optionally protected by environment approval).

## Post-Publish Verification

```bash
python -m venv /tmp/gss-release-test
source /tmp/gss-release-test/bin/activate
pip install --upgrade pip
pip install global-support-standard==0.2.0
gss --help
```

## Rollback Notes

- Do not overwrite or yank tags silently.
- If a bad release is published, create a new patch release with a corrected version.
- Document incident and mitigation in `CHANGELOG.md`.
